import { useEffect, useState } from "react";
import { useAuth } from "../../context/AuthContext";
import { api, ApiError } from "../../api/client";
import { SUBJECTS } from "../../lib/roles";
import Panel from "./Panel";
import Tabs from "./Tabs";

const EXAM_TYPES = ["term1", "term2", "term3", "final"];

function computeGrade(average) {
  if (average === null || average === undefined) return "";
  if (average >= 91) return "S";
  if (average >= 80) return "A+";
  if (average >= 70) return "A";
  if (average >= 60) return "B";
  if (average >= 50) return "C";
  if (average >= 40) return "D";
  return "F";
}

function todayIso() {
  return new Date().toISOString().slice(0, 10);
}

/**
 * The teacher-facing structured workflows (Flow C, D, E from the
 * directive): an interactive attendance grid, an interactive marks
 * grid with real-time total/average/grade, sending a warning, and
 * reading the teacher's own inbox. Everything here calls the same
 * REST endpoints main.py exposes for these flows -- authorization is
 * still fully enforced server-side (authz.verify_teacher_access etc.);
 * this component only ever shows the teacher class/section options
 * their own profile actually lists.
 */
export default function TeacherWorkspace() {
  const { session } = useAuth();
  const [tab, setTab] = useState("attendance");
  const [profile, setProfile] = useState(null);
  const [profileError, setProfileError] = useState(null);

  useEffect(() => {
    if (!session) return;
    api
      .teacherProfile(session.token, session.id)
      .then(setProfile)
      .catch((err) => setProfileError(err.message || "Could not load your teacher profile."));
  }, [session]);

  const classes = profile?.classes || [];
  const sections = profile?.sections || [];
  const handledSubjects = profile?.subject_handled || [];

  return (
    <Panel title="Class workspace" subtitle="Attendance, marks, warnings, and your inbox -- same authorized actions as chat, in table form.">
      {profileError && <p className="mb-3 text-xs text-rust-600">{profileError}</p>}
      <Tabs
        tab={tab}
        onChange={setTab}
        items={[
          { key: "attendance", label: "Attendance" },
          { key: "marks", label: "Marks entry" },
          { key: "warning", label: "Send warning" },
          { key: "inbox", label: "Inbox" },
        ]}
      />
      {tab === "attendance" && <AttendanceGrid classes={classes} sections={sections} />}
      {tab === "marks" && <MarksGrid classes={classes} sections={sections} handledSubjects={handledSubjects} />}
      {tab === "warning" && <SendWarningForm />}
      {tab === "inbox" && <TeacherInbox />}
    </Panel>
  );
}

function ClassSectionPicker({ classes, sections, className, section, setClassName, setSection }) {
  return (
    <div className="grid gap-3 sm:grid-cols-2">
      <div>
        <label className="mb-1 block text-xs font-medium uppercase tracking-wide text-ink-400">Class</label>
        <select
          value={className}
          onChange={(e) => setClassName(e.target.value)}
          className="w-full rounded-xl border border-chalk-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-marigold-400"
        >
          <option value="">Select class…</option>
          {classes.map((c) => (
            <option key={c} value={c}>
              {c}
            </option>
          ))}
        </select>
      </div>
      <div>
        <label className="mb-1 block text-xs font-medium uppercase tracking-wide text-ink-400">Section</label>
        <select
          value={section}
          onChange={(e) => setSection(e.target.value)}
          className="w-full rounded-xl border border-chalk-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-marigold-400"
        >
          <option value="">Select section…</option>
          {sections.map((s) => (
            <option key={s} value={s}>
              {s}
            </option>
          ))}
        </select>
      </div>
    </div>
  );
}

function AttendanceGrid({ classes, sections }) {
  const { session } = useAuth();
  const [className, setClassName] = useState("");
  const [section, setSection] = useState("");
  const [markDate, setMarkDate] = useState(todayIso());
  const [students, setStudents] = useState(null);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);
  const [result, setResult] = useState(null);

  const load = async () => {
    if (!className || !section) {
      setError("Choose a class and section first.");
      return;
    }
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      const data = await api.getClassAttendance(session.token, { className, section, markDate });
      setStudents(data.students);
    } catch (err) {
      setError(err.message || "Could not load the class roster.");
      setStudents(null);
    } finally {
      setLoading(false);
    }
  };

  const toggle = (studentId) => {
    setStudents((prev) =>
      prev.map((s) => (s.student_id === studentId ? { ...s, status: s.status === "P" ? "A" : "P" } : s))
    );
  };

  const save = async () => {
    setSaving(true);
    setError(null);
    setResult(null);
    try {
      const records = students.map((s) => ({ student_id: s.student_id, status: s.status }));
      const data = await api.saveClassAttendance(session.token, { className, section, markDate, records });
      setResult(data.results);
    } catch (err) {
      setError(err.message || "Could not save attendance.");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="space-y-4">
      <ClassSectionPicker classes={classes} sections={sections} className={className} section={section} setClassName={setClassName} setSection={setSection} />
      <div className="flex flex-wrap items-end gap-3">
        <div>
          <label className="mb-1 block text-xs font-medium uppercase tracking-wide text-ink-400">Date</label>
          <input
            type="date"
            value={markDate}
            onChange={(e) => setMarkDate(e.target.value)}
            className="rounded-xl border border-chalk-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-marigold-400"
          />
        </div>
        <button
          type="button"
          onClick={load}
          disabled={loading}
          className="rounded-xl bg-chalk-800 px-4 py-2 text-sm font-medium text-chalk-25 hover:bg-chalk-600 disabled:opacity-50"
        >
          {loading ? "Loading…" : "Load class"}
        </button>
      </div>

      {error && <p className="text-xs text-rust-600">{error}</p>}

      {students && (
        <>
          <div className="overflow-hidden rounded-xl ring-1 ring-chalk-200">
            <table className="w-full text-left text-sm">
              <thead className="bg-chalk-25 text-xs uppercase tracking-wide text-ink-400">
                <tr>
                  <th className="px-4 py-2">Student ID</th>
                  <th className="px-4 py-2">Name</th>
                  <th className="px-4 py-2">Attendance</th>
                </tr>
              </thead>
              <tbody>
                {students.map((s) => (
                  <tr key={s.student_id} className="border-t border-chalk-100">
                    <td className="px-4 py-2 font-mono text-xs text-ink-400">{s.student_id}</td>
                    <td className="px-4 py-2 text-ink-900">{s.name}</td>
                    <td className="px-4 py-2">
                      <button
                        type="button"
                        onClick={() => toggle(s.student_id)}
                        className={`w-16 rounded-lg py-1 text-xs font-semibold uppercase tracking-wide text-white transition ${
                          s.status === "P" ? "bg-chalk-400 hover:bg-chalk-600" : "bg-rust-500 hover:bg-rust-600"
                        }`}
                      >
                        {s.status === "P" ? "Present" : "Absent"}
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <button
            type="button"
            onClick={save}
            disabled={saving}
            className="rounded-xl bg-marigold-400 px-4 py-2 text-sm font-semibold text-ink-900 hover:bg-marigold-500 disabled:opacity-50"
          >
            {saving ? "Saving…" : "Save attendance"}
          </button>
        </>
      )}

      {result && (
        <p className="text-xs text-chalk-600">
          Saved {result.filter((r) => r.action).length}/{result.length} record(s).
        </p>
      )}
    </div>
  );
}

function MarksGrid({ classes, sections, handledSubjects }) {
  const { session } = useAuth();
  const [className, setClassName] = useState("");
  const [section, setSection] = useState("");
  const [examType, setExamType] = useState("term1");
  const [roster, setRoster] = useState(null);
  const [marks, setMarks] = useState({}); // student_id -> { Subject: value }
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);
  const [results, setResults] = useState(null);

  const editableSubjects = SUBJECTS.filter((s) => handledSubjects.includes(s));

  const load = async () => {
    if (!className || !section) {
      setError("Choose a class and section first.");
      return;
    }
    setLoading(true);
    setError(null);
    setResults(null);
    try {
      // There is no GET /marks/class read endpoint yet -- the roster
      // (student_id + name) is fetched from the attendance grid endpoint,
      // which every teacher can already call for their own class/section.
      // Existing marks are therefore not pre-filled here; entries start
      // blank rather than showing invented/stale numbers.
      const data = await api.getClassAttendance(session.token, { className, section });
      setRoster(data.students);
      setMarks(Object.fromEntries(data.students.map((s) => [s.student_id, {}])));
    } catch (err) {
      setError(err.message || "Could not load the class roster.");
      setRoster(null);
    } finally {
      setLoading(false);
    }
  };

  const setMark = (studentId, subject, value) => {
    setMarks((prev) => ({
      ...prev,
      [studentId]: { ...prev[studentId], [subject]: value === "" ? undefined : Number(value) },
    }));
  };

  const rowStats = (studentId) => {
    const row = marks[studentId] || {};
    const values = Object.values(row).filter((v) => v !== undefined && !Number.isNaN(v));
    if (!values.length) return { total: null, average: null, grade: "" };
    const total = values.reduce((a, b) => a + b, 0);
    const average = total / values.length;
    return { total: Math.round(total * 100) / 100, average: Math.round(average * 100) / 100, grade: computeGrade(average) };
  };

  const save = async () => {
    setSaving(true);
    setError(null);
    setResults(null);
    try {
      const records = roster.map((s) => ({ student_id: s.student_id, ...marks[s.student_id] }));
      const data = await api.saveClassMarks(session.token, { className, section, examType, records });
      setResults(data.results);
    } catch (err) {
      setError(err.message || "Could not save marks.");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="space-y-4">
      <ClassSectionPicker classes={classes} sections={sections} className={className} section={section} setClassName={setClassName} setSection={setSection} />
      <div className="flex flex-wrap items-end gap-3">
        <div>
          <label className="mb-1 block text-xs font-medium uppercase tracking-wide text-ink-400">Exam type</label>
          <select
            value={examType}
            onChange={(e) => setExamType(e.target.value)}
            className="rounded-xl border border-chalk-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-marigold-400"
          >
            {EXAM_TYPES.map((t) => (
              <option key={t} value={t}>
                {t}
              </option>
            ))}
          </select>
        </div>
        <button
          type="button"
          onClick={load}
          disabled={loading}
          className="rounded-xl bg-chalk-800 px-4 py-2 text-sm font-medium text-chalk-25 hover:bg-chalk-600 disabled:opacity-50"
        >
          {loading ? "Loading…" : "Load class"}
        </button>
      </div>

      {editableSubjects.length === 0 && profileHint()}
      {error && <p className="text-xs text-rust-600">{error}</p>}

      {roster && (
        <>
          <div className="overflow-x-auto rounded-xl ring-1 ring-chalk-200">
            <table className="w-full min-w-[720px] text-left text-sm">
              <thead className="bg-chalk-25 text-xs uppercase tracking-wide text-ink-400">
                <tr>
                  <th className="px-3 py-2">Student</th>
                  {SUBJECTS.map((subject) => (
                    <th key={subject} className="px-3 py-2">
                      {subject}
                      {!editableSubjects.includes(subject) && <span className="ml-1 text-[10px] normal-case text-ink-400">(not yours)</span>}
                    </th>
                  ))}
                  <th className="px-3 py-2">Total</th>
                  <th className="px-3 py-2">Average</th>
                  <th className="px-3 py-2">Grade</th>
                </tr>
              </thead>
              <tbody>
                {roster.map((s) => {
                  const stats = rowStats(s.student_id);
                  return (
                    <tr key={s.student_id} className="border-t border-chalk-100">
                      <td className="px-3 py-2">
                        <span className="block text-ink-900">{s.name}</span>
                        <span className="block font-mono text-[10px] text-ink-400">{s.student_id}</span>
                      </td>
                      {SUBJECTS.map((subject) => (
                        <td key={subject} className="px-3 py-2">
                          <input
                            type="number"
                            min={0}
                            max={100}
                            disabled={!editableSubjects.includes(subject)}
                            value={marks[s.student_id]?.[subject] ?? ""}
                            onChange={(e) => setMark(s.student_id, subject, e.target.value)}
                            className="w-16 rounded-lg border border-chalk-200 px-2 py-1 text-sm focus:outline-none focus:ring-2 focus:ring-marigold-400 disabled:bg-chalk-25 disabled:text-ink-400"
                          />
                        </td>
                      ))}
                      <td className="px-3 py-2 font-medium text-ink-900">{stats.total ?? "—"}</td>
                      <td className="px-3 py-2 font-medium text-ink-900">{stats.average ?? "—"}</td>
                      <td className="px-3 py-2 font-semibold text-chalk-600">{stats.grade || "—"}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          <button
            type="button"
            onClick={save}
            disabled={saving}
            className="rounded-xl bg-marigold-400 px-4 py-2 text-sm font-semibold text-ink-900 hover:bg-marigold-500 disabled:opacity-50"
          >
            {saving ? "Saving…" : "Save marks"}
          </button>
        </>
      )}

      {results && (
        <ul className="space-y-1 text-xs text-ink-600">
          {results.map((r) => (
            <li key={r.student_id}>
              <span className="font-mono text-[10px] text-ink-400">{r.student_id}</span>{" "}
              {r.error ? <span className="text-rust-600">{r.error}</span> : `total ${r.total}, average ${r.average}, grade ${r.grade}`}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function profileHint() {
  return (
    <p className="text-xs text-ink-400">
      You don&rsquo;t handle any of the five subjects on file, so no columns are editable here.
    </p>
  );
}

function SendWarningForm() {
  const { session } = useAuth();
  const [targetStudentId, setTargetStudentId] = useState("");
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
      const data = await api.sendWarning(session.token, { targetStudentId, messageContent });
      setNotice(`Warning sent to ${data.student_name}.`);
      setTargetStudentId("");
      setMessageContent("");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not send the warning.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <form className="max-w-md space-y-3" onSubmit={submit}>
      <div>
        <label className="mb-1 block text-xs font-medium uppercase tracking-wide text-ink-400">Target student ID</label>
        <input
          value={targetStudentId}
          onChange={(e) => setTargetStudentId(e.target.value)}
          placeholder="e.g. S001"
          required
          className="w-full rounded-xl border border-chalk-200 px-4 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-marigold-400"
        />
        <p className="mt-1 text-[11px] text-ink-400">Must be a student in your own assigned class/section.</p>
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
      <button type="submit" disabled={busy} className="rounded-xl bg-rust-500 px-4 py-2 text-sm font-semibold text-white hover:bg-rust-600 disabled:opacity-50">
        {busy ? "Sending…" : "Send warning"}
      </button>
      {notice && <p className="text-xs text-chalk-600">{notice}</p>}
      {error && <p className="text-xs text-rust-600">{error}</p>}
    </form>
  );
}

function TeacherInbox() {
  const { session } = useAuth();
  const [unreadOnly, setUnreadOnly] = useState(false);
  const [messages, setMessages] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(false);

  const load = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await api.myCommunications(session.token, { unreadOnly });
      setMessages(data.messages);
    } catch (err) {
      setError(err.message || "Could not load your inbox.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [unreadOnly]);

  return (
    <div className="space-y-3">
      <label className="flex items-center gap-2 text-xs text-ink-600">
        <input type="checkbox" checked={unreadOnly} onChange={(e) => setUnreadOnly(e.target.checked)} />
        Unread only
      </label>
      {loading && <p className="text-xs text-ink-400">Loading…</p>}
      {error && <p className="text-xs text-rust-600">{error}</p>}
      {messages && messages.length === 0 && <p className="text-xs text-ink-400">No messages.</p>}
      <ul className="space-y-2">
        {messages?.map((m) => (
          <li key={m.id} className="rounded-lg bg-white p-3 ring-1 ring-chalk-200">
            <div className="flex items-center justify-between text-[10px] uppercase tracking-wide text-ink-400">
              <span>
                {m.type} from {m.from_role} ({m.from_id})
              </span>
              <span>{m.created_at ? new Date(m.created_at).toLocaleString() : ""}</span>
            </div>
            {m.subject && <p className="mt-1 text-[11px] text-marigold-600">Subject: {m.subject}</p>}
            <p className="mt-1 text-sm text-ink-900">{m.content}</p>
          </li>
        ))}
      </ul>
    </div>
  );
}
