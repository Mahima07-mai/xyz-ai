"""
Conversation memory.

Keyed by the VERIFIED caller id from auth.get_current_user() (caller["id"]),
which under the Phase 2 schema is a per-role string primary key
(teacher_id / student_id / principal_id) or a UUID string (parent_id) --
never an integer `user_id`, since there is no more single User table.

A "turn" here is one OpenAI-style message dict (system messages are never
stored -- they're re-added fresh from personas.py every request). Tool-call
/ tool-result message pairs count as part of the turn they belong to and
are trimmed together so a trimmed history never starts mid-tool-call.
"""
import threading

MAX_USER_TURNS = 12


class SessionStore:
    """Per-caller-id conversation history store. Thread-safe enough for a
    single-process FastAPI dev server; a Redis-backed implementation would
    keep this exact interface."""

    def __init__(self, max_user_turns: int = MAX_USER_TURNS):
        self._max_user_turns = max_user_turns
        self._by_caller: dict[str, list[dict]] = {}
        self._lock = threading.Lock()

    def get(self, caller_id: str) -> list[dict]:
        with self._lock:
            return list(self._by_caller.get(str(caller_id), []))

    def set(self, caller_id: str, history: list[dict]) -> None:
        with self._lock:
            self._by_caller[str(caller_id)] = self._trim(history)

    def clear(self, caller_id: str) -> None:
        with self._lock:
            self._by_caller.pop(str(caller_id), None)

    def _trim(self, history: list[dict]) -> list[dict]:
        user_indices = [i for i, m in enumerate(history) if m.get("role") == "user"]
        if len(user_indices) <= self._max_user_turns:
            return history
        cutoff = user_indices[-self._max_user_turns]
        return history[cutoff:]


conversation_store = SessionStore()
