import { useCallback, useEffect, useState } from "react";
import { api } from "../api/client";
import { useAuth } from "../context/AuthContext";

const STATUS_STYLE = {
  confirmed: "bg-chalk-400/15 text-chalk-600 ring-chalk-400/30",
  pending: "bg-marigold-400/15 text-marigold-600 ring-marigold-400/30",
  failed: "bg-rust-400/15 text-rust-600 ring-rust-400/30",
};

/**
 * Reads GET /escalations/mine -- the same EscalationRequest rows the
 * assistant's chat replies are required to describe truthfully (see
 * backend/app/escalation.py's module docstring). Showing this panel
 * alongside the chat is what makes the project plan's "no false success
 * claims" requirement (section 1.4/1.7) demonstrable rather than just
 * asserted: whatever the assistant just said in chat and what this
 * panel shows must always agree, because both read the same row.
 *
 * `refreshSignal` is bumped by the parent after every chat turn so a
 * just-created escalation shows up without a manual refresh.
 */
export default function EscalationPanel({ refreshSignal }) {
  const { session } = useAuth();
  const [escalations, setEscalations] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const load = useCallback(async () => {
    if (!session) return;
    setLoading(true);
    setError(null);
    try {
      const { escalations: rows } = await api.myEscalations(session.token);
      setEscalations(rows);
    } catch (err) {
      setError(err.message || "Could not load escalation history.");
    } finally {
      setLoading(false);
    }
  }, [session]);

  useEffect(() => {
    load();
  }, [load, refreshSignal]);

  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center justify-between">
        <h3 className="font-display text-sm font-semibold text-ink-900">Escalation history</h3>
        <button
          type="button"
          onClick={load}
          className="font-mono text-[11px] uppercase tracking-wide text-chalk-600 hover:text-chalk-800"
        >
          {loading ? "Refreshing…" : "Refresh"}
        </button>
      </div>
      <p className="mt-1 text-xs text-ink-400">
        The true, current status of every human-escalation request you&rsquo;ve made. What the
        assistant tells you in chat will always match this.
      </p>

      {error && <p className="mt-3 text-xs text-rust-600">{error}</p>}

      {!error && escalations.length === 0 && !loading && (
        <p className="mt-4 rounded-lg border border-dashed border-chalk-200 px-3 py-4 text-center text-xs text-ink-400">
          No escalations requested yet. Ask to speak with a person if you ever need one.
        </p>
      )}

      <ul className="mt-3 flex-1 space-y-2 overflow-y-auto pr-1">
        {escalations.map((e) => (
          <li key={e.id} className="rounded-lg bg-white/70 p-3 ring-1 ring-chalk-200">
            <div className="flex items-center justify-between gap-2">
              <span
                className={`rounded-full px-2 py-0.5 font-mono text-[10px] font-medium uppercase tracking-wide ring-1 ${STATUS_STYLE[e.status]}`}
              >
                {e.status}
              </span>
              <span className="font-mono text-[10px] text-ink-400">
                {e.created_at ? new Date(e.created_at).toLocaleString() : ""}
              </span>
            </div>
            <p className="mt-1.5 text-xs text-ink-600">{e.reason}</p>
          </li>
        ))}
      </ul>
    </div>
  );
}
