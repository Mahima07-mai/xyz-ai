import { useCallback, useEffect, useRef, useState } from "react";
import { api, ApiError } from "../api/client";
import { useAuth } from "../context/AuthContext";

/**
 * Shared chat state/logic for the ChatWidget, so all four portals get
 * byte-identical behavior against POST /chat and POST /chat/reset (the
 * project plan's Day 3 "one chat widget component" requirement) rather
 * than four re-implementations that could drift.
 *
 * The backend, not this hook, is the source of truth for conversation
 * history (backend/app/sessions.py keeps it server-side, keyed by the
 * verified caller id from the JWT -- a role-scoped string, not an
 * integer user_id). This hook only keeps a local *display* transcript
 * so the
 * UI has something to render immediately; every reply still comes from
 * a real round trip to /chat.
 */
export function useChat() {
  const { session, logout } = useAuth();
  const [messages, setMessages] = useState([]);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState(null);
  const nextLocalId = useRef(0);

  // Fresh transcript whenever the signed-in user changes (e.g. someone
  // logs out and a different demo account logs in on the same tab).
  useEffect(() => {
    setMessages([]);
    setError(null);
  }, [session?.id]);

  const pushMessage = useCallback((msg) => {
    nextLocalId.current += 1;
    setMessages((prev) => [...prev, { id: nextLocalId.current, ...msg }]);
  }, []);

  const sendMessage = useCallback(
    async (text) => {
      const trimmed = text.trim();
      if (!trimmed || pending || !session) return;

      setError(null);
      pushMessage({ role: "user", content: trimmed, at: Date.now() });
      setPending(true);
      try {
        const { reply } = await api.sendChatMessage(session.token, trimmed);
        pushMessage({ role: "assistant", content: reply, at: Date.now() });
      } catch (err) {
        if (err instanceof ApiError && err.status === 401) {
          setError("Your session expired. Please sign in again.");
          logout();
        } else {
          setError(err.message || "Something went wrong sending that message.");
        }
      } finally {
        setPending(false);
      }
    },
    [pending, session, pushMessage, logout]
  );

  const resetConversation = useCallback(async () => {
    if (!session) return;
    setError(null);
    try {
      await api.resetChat(session.token);
      setMessages([]);
    } catch (err) {
      setError(err.message || "Could not reset the conversation.");
    }
  }, [session]);

  return { messages, pending, error, sendMessage, resetConversation };
}
