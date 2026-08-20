import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { api, ApiError } from "../api/client";
import { decodeJwtPayloadUnsafe } from "../lib/jwt";

/**
 * Session state for the app. Wraps POST /auth/login (role + identifier +
 * password -- backend/app/auth.py) and holds the resulting session token
 * exactly as the backend issued it.
 *
 * Identity is always (role, id-within-that-role-table) under the
 * role-scoped schema -- teacher_id/student_id/principal_id are strings
 * ("T001"), and parent_id is a UUID string. `session.id` is therefore
 * always kept as the raw string from the token's `sub` claim; it is
 * NEVER coerced with Number(), which would silently turn "T001" into
 * NaN and quietly break every downstream display and lookup that uses
 * it (e.g. a teacher looking up their own profile by ID).
 *
 * sessionStorage (not localStorage) on purpose: it clears when the tab
 * closes, which suits a token with a 2-hour expiry (backend/app/auth.py
 * JWT_EXPIRY_MINUTES) better than a token that silently lingers across
 * browser sessions.
 */
const AuthContext = createContext(null);

const STORAGE_KEY = "xyz-ai.session";

export function AuthProvider({ children }) {
  const [session, setSession] = useState(() => {
    const raw = sessionStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    try {
      return JSON.parse(raw);
    } catch {
      return null;
    }
  });

  useEffect(() => {
    if (session) {
      sessionStorage.setItem(STORAGE_KEY, JSON.stringify(session));
    } else {
      sessionStorage.removeItem(STORAGE_KEY);
    }
  }, [session]);

  const login = useCallback(async (role, identifier, password) => {
    const { access_token: token } = await api.login({ role, identifier, password });
    const claims = decodeJwtPayloadUnsafe(token);
    if (!claims) {
      throw new ApiError("Received a session token the app could not read. Please try again.", 500);
    }
    const nextSession = {
      token,
      id: String(claims.sub),
      role: claims.role,
      name: claims.name,
      expiresAt: claims.exp ? claims.exp * 1000 : null,
    };
    setSession(nextSession);
    return nextSession;
  }, []);

  const logout = useCallback(() => setSession(null), []);

  // Passive expiry check: if the token's own exp has passed, treat the
  // session as logged out rather than letting requests fail with a
  // confusing 401 mid-conversation. The backend independently rejects
  // an expired token regardless (auth.decode_session_token) -- this is
  // just a friendlier client-side mirror of that same rule.
  useEffect(() => {
    if (!session?.expiresAt) return undefined;
    const msRemaining = session.expiresAt - Date.now();
    if (msRemaining <= 0) {
      setSession(null);
      return undefined;
    }
    const timer = setTimeout(() => setSession(null), msRemaining);
    return () => clearTimeout(timer);
  }, [session]);

  const value = useMemo(
    () => ({ session, isAuthenticated: !!session, login, logout }),
    [session, login, logout]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within an AuthProvider");
  return ctx;
}
