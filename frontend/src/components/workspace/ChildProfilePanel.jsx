import { useState } from "react";
import { useAuth } from "../../context/AuthContext";
import { api, ApiError } from "../../api/client";
import Panel from "./Panel";

/**
 * Flow E bio lookup for a parent. The parent's linked child isn't part
 * of the JWT (identity there is only the parent's own parent_id), so
 * this asks for the child's student ID the parent already knows from
 * registration (auth.ParentRegisterRequest.child_student_id) and looks
 * it up via GET /principal/student/{id} -- authz.verify_student_bio_access
 * only returns data if that ID really is this parent's linked child;
 * anything else comes back as an honest 403, never silently succeeds.
 */
export default function ChildProfilePanel() {
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
      setError(err instanceof ApiError ? err.message : "Could not load your child's profile.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <Panel title="My child's profile" subtitle="Enter your linked child's Student ID to view their bio details.">
      <form className="flex max-w-md gap-2" onSubmit={lookup}>
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
      {error && <p className="mt-3 text-xs text-rust-600">{error}</p>}
      {profile && (
        <dl className="mt-4 grid grid-cols-2 gap-3 text-sm sm:grid-cols-3">
          <Detail label="Name" value={profile.name} />
          <Detail label="Class" value={`${profile.class_name} - ${profile.section}`} />
          <Detail label="Gender" value={profile.gender} />
          <Detail label="Date of birth" value={profile.date_of_birth} />
          <Detail label="Guardian" value={profile.guardian_name} />
          <Detail label="Contact" value={profile.contact_number} />
          <Detail label="Blood group" value={profile.blood_group} />
          <Detail label="Overall average" value={profile.overall_average_score} />
        </dl>
      )}
    </Panel>
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
