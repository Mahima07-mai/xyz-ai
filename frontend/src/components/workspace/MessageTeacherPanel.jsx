import { useState } from "react";
import { useAuth } from "../../context/AuthContext";
import { api, ApiError } from "../../api/client";
import { SUBJECTS } from "../../lib/roles";
import Panel from "./Panel";

/**
 * Flow E: "Option to send a message/doubt to an assigned teacher" for
 * students, and the parent-query equivalent. Both roles call the same
 * POST /communications/ask endpoint (tools.ask_teacher) -- the backend
 * derives "doubt" vs. "parent_query" from the caller's verified role,
 * and verify_teacher_communication_access rejects a teacher who doesn't
 * actually teach the caller's (or linked child's) class/section, so a
 * wrong teacher_id here surfaces as a normal, honest error rather than
 * silently succeeding.
 */
export default function MessageTeacherPanel({ role }) {
  const { session } = useAuth();
  const [targetTeacherId, setTargetTeacherId] = useState("");
  const [subject, setSubject] = useState("");
  const [messageContent, setMessageContent] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [notice, setNotice] = useState(null);

  const submit = async (e) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      await api.askTeacher(session.token, { targetTeacherId, messageContent, subject: subject || undefined });
      setNotice("Message sent.");
      setTargetTeacherId("");
      setSubject("");
      setMessageContent("");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not send the message.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <Panel
      title="Message a teacher"
      subtitle={
        role === "parent"
          ? "Send a query to a teacher who teaches your linked child's class and section."
          : "Send a doubt to a teacher who teaches your class and section."
      }
    >
      <form className="max-w-md space-y-3" onSubmit={submit}>
        <div>
          <label className="mb-1 block text-xs font-medium uppercase tracking-wide text-ink-400">Teacher ID</label>
          <input
            value={targetTeacherId}
            onChange={(e) => setTargetTeacherId(e.target.value)}
            placeholder="e.g. T001"
            required
            className="w-full rounded-xl border border-chalk-200 px-4 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-marigold-400"
          />
        </div>
        <div>
          <label className="mb-1 block text-xs font-medium uppercase tracking-wide text-ink-400">Subject (optional)</label>
          <select
            value={subject}
            onChange={(e) => setSubject(e.target.value)}
            className="w-full rounded-xl border border-chalk-200 px-4 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-marigold-400"
          >
            <option value="">No specific subject</option>
            {SUBJECTS.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label className="mb-1 block text-xs font-medium uppercase tracking-wide text-ink-400">Message</label>
          <textarea
            value={messageContent}
            onChange={(e) => setMessageContent(e.target.value)}
            rows={3}
            required
            className="w-full rounded-xl border border-chalk-200 px-4 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-marigold-400"
          />
        </div>
        <button type="submit" disabled={busy} className="rounded-xl bg-marigold-400 px-4 py-2 text-sm font-semibold text-ink-900 hover:bg-marigold-500 disabled:opacity-50">
          {busy ? "Sending…" : "Send message"}
        </button>
        {notice && <p className="text-xs text-chalk-600">{notice}</p>}
        {error && <p className="text-xs text-rust-600">{error}</p>}
      </form>
    </Panel>
  );
}
