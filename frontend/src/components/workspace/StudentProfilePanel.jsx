import { useEffect, useState } from "react";
import { useAuth } from "../../context/AuthContext";
import { api } from "../../api/client";
import Panel from "./Panel";

/**
 * Flow E: "Standard report displaying ... Bio details" for the student's
 * own profile. Calls GET /principal/student/{id} with the student's own
 * verified id -- despite the path, tools.get_student_profile ->
 * authz.verify_student_bio_access explicitly allows a student to fetch
 * their own record this way, same as the chat tools do.
 */
export default function StudentProfilePanel() {
  const { session } = useAuth();
  const [profile, setProfile] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!session) return;
    api
      .studentProfile(session.token, session.id)
      .then(setProfile)
      .catch((err) => setError(err.message || "Could not load your profile."))
      .finally(() => setLoading(false));
  }, [session]);

  return (
    <Panel title="My profile" subtitle="Bio details on file for your account.">
      {loading && <p className="text-xs text-ink-400">Loading…</p>}
      {error && <p className="text-xs text-rust-600">{error}</p>}
      {profile && (
        <dl className="grid grid-cols-2 gap-3 text-sm sm:grid-cols-3">
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
