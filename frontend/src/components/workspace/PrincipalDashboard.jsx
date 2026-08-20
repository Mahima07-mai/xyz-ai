import { useEffect, useState } from "react";
import { useAuth } from "../../context/AuthContext";
import { api } from "../../api/client";
import { SUBJECTS } from "../../lib/roles";
import Panel from "./Panel";
import Tabs from "./Tabs";

/**
 * Flow F: the principal's school-wide dashboard -- the class/section
 * summary grid with key metric cards, a subject-based teacher search,
 * and student/teacher bio lookups. Every call here is read-only and
 * goes through authz.verify_principal_access / verify_*_bio_access on
 * the backend exactly like a chat-driven lookup would; this is just a
 * faster, table-shaped way to reach the same authorized data.
 */
export default function PrincipalDashboard() {
  const [tab, setTab] = useState("grid");

  return (
    <Panel title="Management dashboard" subtitle="School-wide summary, staffing search, and profile lookups.">
      <Tabs
        tab={tab}
        onChange={setTab}
        items={[
          { key: "grid", label: "Summary grid" },
          { key: "teachers", label: "Teachers by subject" },
          { key: "student", label: "Student lookup" },
          { key: "teacher", label: "Teacher lookup" },
        ]}
      />
      {tab === "grid" && <SummaryGrid />}
      {tab === "teachers" && <TeachersBySubject />}
      {tab === "student" && <StudentLookup />}
      {tab === "teacher" && <TeacherLookup />}
    </Panel>
  );
}

function MetricCard({ label, value }) {
  return (
    <div className="rounded-xl bg-white px-4 py-3 text-center ring-1 ring-chalk-200">
      <p className="font-display text-2xl font-semibold text-ink-900">{value}</p>
      <p className="mt-0.5 text-[10px] uppercase tracking-wide text-ink-400">{label}</p>
    </div>
  );
}

function SummaryGrid() {
  const { session } = useAuth();
  const [grid, setGrid] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    api
      .summaryGrid(session.token)
      .then((data) => setGrid(data.grid))
      .catch((err) => setError(err.message || "Could not load the summary grid."))
      .finally(() => setLoading(false));
  }, [session]);

  if (loading) return <p className="text-xs text-ink-400">Loading…</p>;
  if (error) return <p className="text-xs text-rust-600">{error}</p>;
  if (!grid) return null;

  const totalStudents = grid.reduce((sum, cell) => sum + cell.student_count, 0);
  const uniqueTeachers = new Set(grid.flatMap((cell) => cell.teachers.map((t) => t.teacher_id))).size;

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
        <MetricCard label="Total students" value={totalStudents} />
        <MetricCard label="Classes / sections" value={grid.length} />
        <MetricCard label="Teachers on file" value={uniqueTeachers} />
      </div>
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {grid.map((cell) => (
          <div key={`${cell.class_name}-${cell.section}`} className="rounded-xl bg-white p-4 ring-1 ring-chalk-200">
            <div className="flex items-center justify-between">
              <p className="font-display text-base font-semibold text-ink-900">
                Class {cell.class_name} · {cell.section}
              </p>
              <span className="rounded-full bg-chalk-100 px-2 py-0.5 text-[10px] font-medium text-chalk-800">
                {cell.student_count} student{cell.student_count === 1 ? "" : "s"}
              </span>
            </div>
            <ul className="mt-2 space-y-1">
              {cell.teachers.length === 0 && <li className="text-xs text-ink-400">No teacher assigned.</li>}
              {cell.teachers.map((t) => (
                <li key={t.teacher_id} className="text-xs text-ink-600">
                  {t.name} <span className="text-ink-400">({(t.subject_handled || []).join(", ")})</span>
                </li>
              ))}
            </ul>
          </div>
        ))}
      </div>
    </div>
  );
}

function TeachersBySubject() {
  const { session } = useAuth();
  const [subject, setSubject] = useState(SUBJECTS[0]);
  const [teachers, setTeachers] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(false);

  const search = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await api.teachersBySubject(session.token, subject);
      setTeachers(data.teachers);
    } catch (err) {
      setError(err.message || "Could not load teachers.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    search();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-end gap-3">
        <div>
          <label className="mb-1 block text-xs font-medium uppercase tracking-wide text-ink-400">Subject</label>
          <select
            value={subject}
            onChange={(e) => setSubject(e.target.value)}
            className="rounded-xl border border-chalk-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-marigold-400"
          >
            {SUBJECTS.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>
        </div>
        <button type="button" onClick={search} disabled={loading} className="rounded-xl bg-chalk-800 px-4 py-2 text-sm font-medium text-chalk-25 hover:bg-chalk-600 disabled:opacity-50">
          {loading ? "Searching…" : "Search"}
        </button>
      </div>
      {error && <p className="text-xs text-rust-600">{error}</p>}
      {teachers && teachers.length === 0 && <p className="text-xs text-ink-400">No teachers handle this subject yet.</p>}
      <ul className="space-y-2">
        {teachers?.map((t) => (
          <li key={t.teacher_id} className="rounded-lg bg-white p-3 ring-1 ring-chalk-200">
            <p className="text-sm font-medium text-ink-900">{t.name}</p>
            <p className="font-mono text-[10px] text-ink-400">{t.teacher_id}</p>
            <p className="mt-1 text-xs text-ink-600">
              Classes {(t.classes || []).join(", ")} · Sections {(t.sections || []).join(", ")}
            </p>
          </li>
        ))}
      </ul>
    </div>
  );
}

function StudentLookup() {
  const { session } = useAuth();
  const [studentId, setStudentId] = useState("");
  const [profile, setProfile] = useState(null);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);

  const lookup = async (e) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    setProfile(null);
    try {
      const data = await api.studentProfile(session.token, studentId.trim());
      setProfile(data);
    } catch (err) {
      setError(err.message || "Could not find that student.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-3">
      <form className="flex gap-2" onSubmit={lookup}>
        <input
          value={studentId}
          onChange={(e) => setStudentId(e.target.value)}
          placeholder="Student ID, e.g. S001"
          required
          className="flex-1 rounded-xl border border-chalk-200 px-4 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-marigold-400"
        />
        <button type="submit" disabled={busy} className="rounded-xl bg-chalk-800 px-4 py-2.5 text-sm font-medium text-chalk-25 hover:bg-chalk-600 disabled:opacity-50">
          {busy ? "Looking up…" : "Look up"}
        </button>
      </form>
      {error && <p className="text-xs text-rust-600">{error}</p>}
      {profile && (
        <dl className="grid grid-cols-2 gap-3 rounded-xl bg-white p-4 text-sm ring-1 ring-chalk-200 sm:grid-cols-3">
          <Detail label="Name" value={profile.name} />
          <Detail label="Class" value={`${profile.class_name} - ${profile.section}`} />
          <Detail label="Gender" value={profile.gender} />
          <Detail label="Date of birth" value={profile.date_of_birth} />
          <Detail label="Guardian" value={profile.guardian_name} />
          <Detail label="Contact" value={profile.contact_number} />
          <Detail label="Blood group" value={profile.blood_group} />
          <Detail label="Overall average" value={profile.overall_average_score} />
          <Detail label="Address" value={profile.address} />
        </dl>
      )}
    </div>
  );
}

function TeacherLookup() {
  const { session } = useAuth();
  const [teacherId, setTeacherId] = useState("");
  const [profile, setProfile] = useState(null);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);

  const lookup = async (e) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    setProfile(null);
    try {
      const data = await api.teacherProfile(session.token, teacherId.trim());
      setProfile(data);
    } catch (err) {
      setError(err.message || "Could not find that teacher.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-3">
      <form className="flex gap-2" onSubmit={lookup}>
        <input
          value={teacherId}
          onChange={(e) => setTeacherId(e.target.value)}
          placeholder="Teacher ID, e.g. T001"
          required
          className="flex-1 rounded-xl border border-chalk-200 px-4 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-marigold-400"
        />
        <button type="submit" disabled={busy} className="rounded-xl bg-chalk-800 px-4 py-2.5 text-sm font-medium text-chalk-25 hover:bg-chalk-600 disabled:opacity-50">
          {busy ? "Looking up…" : "Look up"}
        </button>
      </form>
      {error && <p className="text-xs text-rust-600">{error}</p>}
      {profile && (
        <dl className="grid grid-cols-2 gap-3 rounded-xl bg-white p-4 text-sm ring-1 ring-chalk-200 sm:grid-cols-3">
          <Detail label="Name" value={profile.name} />
          <Detail label="Classes" value={(profile.classes || []).join(", ")} />
          <Detail label="Sections" value={(profile.sections || []).join(", ")} />
          <Detail label="Subjects handled" value={(profile.subject_handled || []).join(", ")} />
          <Detail label="Qualification" value={profile.qualification} />
          <Detail label="Experience (yrs)" value={profile.years_of_experience} />
          <Detail label="Joined" value={profile.joined_date} />
        </dl>
      )}
    </div>
  );
}

function Detail({ label, value }) {
  return (
    <div>
      <dt className="text-[10px] uppercase tracking-wide text-ink-400">{label}</dt>
      <dd className="text-ink-900">{value === null || value === undefined || value === "" ? "—" : String(value)}</dd>
    </div>
  );
}
