/**
 * Decodes the payload of the session JWT issued by POST /auth/login
 * (backend/app/auth.py: issue_session_token) so the UI can greet the
 * user by name/role without a separate "/me" endpoint.
 *
 * DISPLAY ONLY. This is not a verification step -- the signature is
 * never checked here, and nothing in this app makes an authorization
 * decision from the decoded result. Every request that matters
 * (get_own_attendance, mark_attendance, etc.) re-sends the raw token to
 * the backend, which re-verifies the signature and re-derives the role
 * server-side on every call (see backend/app/auth.get_current_user).
 * Decoding here only saves a round trip for a name/role greeting.
 */
export function decodeJwtPayloadUnsafe(token) {
  try {
    const [, payloadB64] = token.split(".");
    const normalized = payloadB64.replace(/-/g, "+").replace(/_/g, "/");
    const padded = normalized.padEnd(normalized.length + ((4 - (normalized.length % 4)) % 4), "=");
    const json = atob(padded);
    return JSON.parse(json);
  } catch {
    return null;
  }
}
