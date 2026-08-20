import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import { ROLE_ORDER, roleMeta, SUBJECTS } from "../lib/roles";
import { api, ApiError } from "../api/client";

const ROUTE_BY_ROLE = {
  student: "/student",
  parent: "/parent",
  teacher: "/staff",
  principal: "/management",
};

const MODES = { SIGN_IN: "sign-in", REGISTER: "register", FORGOT: "forgot" };

const emptyRegisterForm = {
  name: "",
  // role-specific identity field(s):
  teacher_id: "",
  student_id: "",
  child_student_id: "",
  principal_id: "",
  // teacher-only:
  subject_handled: [],
  classes: "",
  sections: "",
  // student-only:
  class_name: "",
  section: "",
  gender: "",
  date_of_birth: "",
  guardian_name: "",
  contact_number: "",
  blood_group: "",
  // shared:
  gmail: "",
  password: "",
  verify_password: "",
};

function splitCsv(value) {
  return value
    .split(",")
    .map((v) => v.trim())
    .filter(Boolean);
}

/** Builds the exact payload each /auth/register/{role} endpoint expects
 * (see backend/app/auth.py's Register*Request pydantic models) -- no
 * extra or renamed fields, so a schema change there is the only place
 * that ever needs to change in lockstep with this function. */
function buildRegisterPayload(role, form) {
  const shared = { name: form.name.trim(), gmail: form.gmail.trim(), password: form.password, verify_password: form.verify_password };
  if (role === "teacher") {
    return {
      ...shared,
      teacher_id: form.teacher_id.trim(),
      subject_handled: form.subject_handled,
      classes: splitCsv(form.classes),
      sections: splitCsv(form.sections),
    };
  }
  if (role === "student") {
    return {
      ...shared,
      student_id: form.student_id.trim(),
      class_name: form.class_name.trim(),
      section: form.section.trim(),
      // NOTE: these are not yet accepted by StudentRegisterRequest in
      // backend/app/auth.py -- they will be sent but silently dropped
      // until that schema (and the StudentBio row it creates) is
      // updated to accept them.
      gender: form.gender.trim(),
      date_of_birth: form.date_of_birth || null,
      guardian_name: form.guardian_name.trim(),
      contact_number: form.contact_number.trim(),
      blood_group: form.blood_group.trim(),
    };
  }
  if (role === "parent") {
    return { ...shared, child_student_id: form.child_student_id.trim() };
  }
  // principal
  return { ...shared, principal_id: form.principal_id.trim() };
}

export default function LoginPortal() {
  const [mode, setMode] = useState(MODES.SIGN_IN);
  const [activeRole, setActiveRole] = useState("student");
  const [identifier, setIdentifier] = useState("");
  const [password, setPassword] = useState("");
  const [registerForm, setRegisterForm] = useState(emptyRegisterForm);
  const [forgotForm, setForgotForm] = useState({ gmail: "", new_password: "", verify_new_password: "" });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [notice, setNotice] = useState(null);
  const { login } = useAuth();
  const navigate = useNavigate();

  const meta = roleMeta(activeRole);

  const switchMode = (nextMode) => {
    setMode(nextMode);
    setError(null);
    setNotice(null);
  };

  const switchRole = (role) => {
    setActiveRole(role);
    setError(null);
    setNotice(null);
    setRegisterForm(emptyRegisterForm);
  };

  const setField = (key) => (e) => setRegisterForm((f) => ({ ...f, [key]: e.target.value }));

  const toggleSubject = (subject) => {
    setRegisterForm((f) => ({
      ...f,
      subject_handled: f.subject_handled.includes(subject)
        ? f.subject_handled.filter((s) => s !== subject)
        : [...f.subject_handled, subject],
    }));
  };

  const handleSignIn = async (e) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const session = await login(activeRole, identifier.trim(), password);
      navigate(ROUTE_BY_ROLE[session.role] || "/");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not sign in. Is the backend running?");
    } finally {
      setBusy(false);
    }
  };

  const handleRegister = async (e) => {
    e.preventDefault();
    if (registerForm.password !== registerForm.verify_password) {
      setError("Password and confirmation do not match.");
      return;
    }
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      const payload = buildRegisterPayload(activeRole, registerForm);
      const registerFn = {
        teacher: api.registerTeacher,
        student: api.registerStudent,
        parent: api.registerParent,
        principal: api.registerPrincipal,
      }[activeRole];
      const created = await registerFn(payload);
      const pkValue = created[meta.pkField] ?? created.teacher_id ?? created.student_id ?? created.principal_id;
      setNotice(`Account created for ${created.name}${pkValue ? ` (${meta.pkLabel}: ${pkValue})` : ""}. You can sign in now.`);
      setRegisterForm(emptyRegisterForm);
      // Parents have no user-chosen ID -- parent_id is a server-generated
      // UUID and login for that role only ever matches on gmail (see
      // backend/app/auth._find_user_by_identifier). Every other role can
      // sign in with either their chosen ID or their gmail, so prefill
      // with the more recognizable ID there.
      setIdentifier(activeRole === "parent" ? registerForm.gmail : pkValue ? String(pkValue) : registerForm.gmail);
      setMode(MODES.SIGN_IN);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not create the account. Is the backend running?");
    } finally {
      setBusy(false);
    }
  };

  const handleForgot = async (e) => {
    e.preventDefault();
    if (forgotForm.new_password !== forgotForm.verify_new_password) {
      setError("New password and confirmation do not match.");
      return;
    }
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      await api.forgotPassword({ role: activeRole, ...forgotForm });
      setNotice("Password updated. You can sign in with your new password now.");
      setForgotForm({ gmail: "", new_password: "", verify_new_password: "" });
      setMode(MODES.SIGN_IN);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not reset the password. Is the backend running?");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="chalkboard flex min-h-screen items-center justify-center px-4 py-10">
      <div className="w-full max-w-2xl rounded-2xl bg-parchment-50 p-8 shadow-chalk">
        <div className="mb-6 text-center">
          <div className="mx-auto mb-3 flex h-12 w-12 items-center justify-center rounded-xl bg-chalk-800 font-display text-xl font-semibold text-marigold-400 shadow-chalk">
            X
          </div>
          <h1 className="font-display text-2xl font-semibold text-ink-900">XYZ AI</h1>
          <p className="mt-1 text-sm text-ink-400">
            {mode === MODES.SIGN_IN && "Sign in with your school account."}
            {mode === MODES.REGISTER && "Create a new account for your role."}
            {mode === MODES.FORGOT && "Reset your password with your registered Gmail."}
          </p>
        </div>

        {/* Role tabs */}
        <div className="mb-5 grid grid-cols-2 gap-2 sm:grid-cols-4">
          {ROLE_ORDER.map((key) => {
            const m = roleMeta(key);
            const active = key === activeRole;
            return (
              <button
                key={key}
                type="button"
                onClick={() => switchRole(key)}
                className={`rounded-xl px-3 py-2.5 text-sm font-medium ring-1 transition ${
                  active
                    ? "bg-chalk-800 text-chalk-25 ring-chalk-800"
                    : "bg-white text-ink-600 ring-chalk-200 hover:bg-chalk-25"
                }`}
              >
                {m.label}
              </button>
            );
          })}
        </div>

        <p className="mb-4 text-xs text-ink-400">{meta.tagline}</p>

        {/* Mode tabs */}
        <div className="mb-5 flex gap-1 rounded-xl bg-white p-1 ring-1 ring-chalk-200">
          {[
            [MODES.SIGN_IN, "Sign in"],
            [MODES.REGISTER, "Create account"],
            [MODES.FORGOT, "Forgot password"],
          ].map(([key, label]) => (
            <button
              key={key}
              type="button"
              onClick={() => switchMode(key)}
              className={`flex-1 rounded-lg px-3 py-1.5 text-xs font-medium transition ${
                mode === key ? "bg-chalk-800 text-chalk-25" : "text-ink-600 hover:bg-chalk-25"
              }`}
            >
              {label}
            </button>
          ))}
        </div>

        {mode === MODES.SIGN_IN && (
          <form className="space-y-3" onSubmit={handleSignIn}>
            <div>
              <label className="mb-1 block text-xs font-medium uppercase tracking-wide text-ink-400">
                {activeRole === "parent" ? "Gmail" : `${meta.pkLabel} or Gmail`}
              </label>
              <input
                value={identifier}
                onChange={(e) => setIdentifier(e.target.value)}
                placeholder={activeRole === "parent" ? "you@gmail.com" : `e.g. ${meta.pkField === "student_id" ? "S001" : meta.pkField === "teacher_id" ? "T001" : "P001"}`}
                required
                className="w-full rounded-xl border border-chalk-200 px-4 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-marigold-400"
              />
            </div>
            <div>
              <label className="mb-1 block text-xs font-medium uppercase tracking-wide text-ink-400">
                Password
              </label>
              <input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
                className="w-full rounded-xl border border-chalk-200 px-4 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-marigold-400"
              />
            </div>
            <button
              type="submit"
              disabled={busy}
              className="w-full rounded-xl bg-chalk-800 px-4 py-2.5 text-sm font-medium text-chalk-25 hover:bg-chalk-600 disabled:opacity-50"
            >
              {busy ? "Signing in…" : "Sign in"}
            </button>
          </form>
        )}

        {mode === MODES.REGISTER && (
          <form className="space-y-3" onSubmit={handleRegister}>
            <div className="grid gap-3 sm:grid-cols-2">
              <Field label="Full name" value={registerForm.name} onChange={setField("name")} required />
              {activeRole === "teacher" && (
                <Field label="Teacher ID (username)" value={registerForm.teacher_id} onChange={setField("teacher_id")} required />
              )}
              {activeRole === "student" && (
                <Field label="Student ID (username)" value={registerForm.student_id} onChange={setField("student_id")} required />
              )}
              {activeRole === "parent" && (
                <Field
                  label="Child's Student ID"
                  value={registerForm.child_student_id}
                  onChange={setField("child_student_id")}
                  required
                  hint="Must already exist -- the child registers their own student account first."
                />
              )}
              {activeRole === "principal" && (
                <Field label="Principal ID (username)" value={registerForm.principal_id} onChange={setField("principal_id")} required />
              )}
            </div>

            {activeRole === "teacher" && (
              <>
                <div className="grid gap-3 sm:grid-cols-2">
                  <Field label="Classes (comma-separated)" value={registerForm.classes} onChange={setField("classes")} placeholder="8, 9" required />
                  <Field label="Sections (comma-separated)" value={registerForm.sections} onChange={setField("sections")} placeholder="A, B" required />
                </div>
                <div>
                  <label className="mb-1.5 block text-xs font-medium uppercase tracking-wide text-ink-400">
                    Subjects handled
                  </label>
                  <div className="flex flex-wrap gap-2">
                    {SUBJECTS.map((s) => (
                      <button
                        key={s}
                        type="button"
                        onClick={() => toggleSubject(s)}
                        className={`rounded-full px-3 py-1.5 text-xs font-medium ring-1 transition ${
                          registerForm.subject_handled.includes(s)
                            ? "bg-marigold-400 text-ink-900 ring-marigold-400"
                            : "bg-white text-ink-600 ring-chalk-200 hover:bg-chalk-25"
                        }`}
                      >
                        {s}
                      </button>
                    ))}
                  </div>
                </div>
              </>
            )}

            {activeRole === "student" && (
              <>
                <div className="grid gap-3 sm:grid-cols-2">
                  <Field label="Class" value={registerForm.class_name} onChange={setField("class_name")} placeholder="8" required />
                  <Field label="Section" value={registerForm.section} onChange={setField("section")} placeholder="A" required />
                </div>
                <div className="grid gap-3 sm:grid-cols-2">
                  <div>
                    <label className="mb-1 block text-xs font-medium uppercase tracking-wide text-ink-400">
                      Gender
                    </label>
                    <select
                      value={registerForm.gender}
                      onChange={setField("gender")}
                      required
                      className="w-full rounded-xl border border-chalk-200 px-4 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-marigold-400"
                    >
                      <option value="" disabled>Select gender</option>
                      <option value="Male">Male</option>
                      <option value="Female">Female</option>
                      <option value="Other">Other</option>
                    </select>
                  </div>
                  <Field
                    label="Date of birth"
                    type="date"
                    value={registerForm.date_of_birth}
                    onChange={setField("date_of_birth")}
                    required
                  />
                </div>
                <div className="grid gap-3 sm:grid-cols-2">
                  <Field label="Guardian name" value={registerForm.guardian_name} onChange={setField("guardian_name")} required />
                  <Field
                    label="Contact number"
                    type="tel"
                    value={registerForm.contact_number}
                    onChange={setField("contact_number")}
                    placeholder="e.g. 9876543210"
                    required
                  />
                </div>
                <div>
                  <label className="mb-1 block text-xs font-medium uppercase tracking-wide text-ink-400">
                    Blood group
                  </label>
                  <select
                    value={registerForm.blood_group}
                    onChange={setField("blood_group")}
                    className="w-full rounded-xl border border-chalk-200 px-4 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-marigold-400"
                  >
                    <option value="">Prefer not to say</option>
                    {["A+", "A-", "B+", "B-", "AB+", "AB-", "O+", "O-"].map((bg) => (
                      <option key={bg} value={bg}>{bg}</option>
                    ))}
                  </select>
                </div>
              </>
            )}

            <Field label="Gmail" type="email" value={registerForm.gmail} onChange={setField("gmail")} required />
            <div className="grid gap-3 sm:grid-cols-2">
              <Field label="Password" type="password" value={registerForm.password} onChange={setField("password")} required hint="At least 8 characters." />
              <Field label="Confirm password" type="password" value={registerForm.verify_password} onChange={setField("verify_password")} required />
            </div>

            <button
              type="submit"
              disabled={busy}
              className="w-full rounded-xl bg-chalk-800 px-4 py-2.5 text-sm font-medium text-chalk-25 hover:bg-chalk-600 disabled:opacity-50"
            >
              {busy ? "Creating account…" : `Create ${meta.label.toLowerCase()} account`}
            </button>
          </form>
        )}

        {mode === MODES.FORGOT && (
          <form className="space-y-3" onSubmit={handleForgot}>
            <Field
              label="Gmail"
              type="email"
              value={forgotForm.gmail}
              onChange={(e) => setForgotForm((f) => ({ ...f, gmail: e.target.value }))}
              required
            />
            <div className="grid gap-3 sm:grid-cols-2">
              <Field
                label="New password"
                type="password"
                value={forgotForm.new_password}
                onChange={(e) => setForgotForm((f) => ({ ...f, new_password: e.target.value }))}
                required
                hint="At least 8 characters."
              />
              <Field
                label="Confirm new password"
                type="password"
                value={forgotForm.verify_new_password}
                onChange={(e) => setForgotForm((f) => ({ ...f, verify_new_password: e.target.value }))}
                required
              />
            </div>
            <button
              type="submit"
              disabled={busy}
              className="w-full rounded-xl bg-chalk-800 px-4 py-2.5 text-sm font-medium text-chalk-25 hover:bg-chalk-600 disabled:opacity-50"
            >
              {busy ? "Updating…" : "Reset password"}
            </button>
          </form>
        )}

        {notice && (
          <div className="mt-4 rounded-lg bg-chalk-400/10 px-3 py-2 text-sm text-chalk-800 ring-1 ring-chalk-400/30">
            {notice}
          </div>
        )}
        {error && (
          <div className="mt-4 rounded-lg bg-rust-500/10 px-3 py-2 text-sm text-rust-600 ring-1 ring-rust-500/30">
            {error}
          </div>
        )}
      </div>
    </div>
  );
}

function Field({ label, hint, className = "", ...inputProps }) {
  return (
    <div className={className}>
      <label className="mb-1 block text-xs font-medium uppercase tracking-wide text-ink-400">{label}</label>
      <input
        {...inputProps}
        className="w-full rounded-xl border border-chalk-200 px-4 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-marigold-400"
      />
      {hint && <p className="mt-1 text-[11px] text-ink-400">{hint}</p>}
    </div>
  );
}
