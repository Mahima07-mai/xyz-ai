/**
 * Thin fetch wrapper around the current backend (backend/app/main.py).
 * Every endpoint here matches the backend route exactly:
 *
 *   POST /auth/register/{role}      { ... role fields ... }      -> { <pk>: str, name }
 *   POST /auth/login                { role, identifier, password} -> { access_token, token_type }
 *   POST /auth/forgot-password      { role, gmail, new_password, verify_new_password } -> { status }
 *   POST /chat                      { message }              (Bearer) -> { reply }
 *   POST /chat/reset                                          (Bearer) -> { status }
 *   GET  /escalations/mine                                    (Bearer) -> { escalations: [...] }
 *   GET  /languages                                                    -> { languages: [...] }
 *   GET  /health                                                       -> { status }
 *
 *   GET  /attendance/class   ?class_name&section&mark_date    (Bearer) -> class roster + status
 *   POST /attendance/class   { class_name, section, mark_date, records } (Bearer) -> save result
 *   POST /marks/class        { class_name, section, exam_type, records } (Bearer) -> save result
 *
 *   POST /communications/warning  { target_student_id, message_content }      (Bearer)
 *   POST /communications/ask      { target_teacher_id, message_content, subject } (Bearer)
 *   GET  /communications/mine     ?unread_only                                (Bearer)
 *
 *   GET  /principal/teachers        ?subject                (Bearer)
 *   GET  /principal/student/{id}                             (Bearer)
 *   GET  /principal/teacher/{id}                             (Bearer)
 *   GET  /principal/summary-grid                             (Bearer)
 *
 * There is no client-side authorization logic anywhere in this file, on
 * purpose -- authorization lives entirely in the backend's authz.py /
 * tools.py layer, keyed off the verified JWT, never off anything this
 * file decides. Several routes here are literally under a "/principal/"
 * path but are also reachable by a teacher/student/parent looking up
 * their OWN record -- that's the backend's authz.verify_*_access rules,
 * not a frontend decision, so this client makes no attempt to hide or
 * second-guess which roles can call which endpoint. A denied call still
 * round-trips to the backend and comes back as a normal ApiError.
 */

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";

class ApiError extends Error {
  constructor(message, status, options) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.options = options || null; // clarification options, e.g. ambiguous student name (409s)
  }
}

async function request(path, { method = "GET", token, body, query } = {}) {
  const headers = { "Content-Type": "application/json" };
  if (token) headers["Authorization"] = `Bearer ${token}`;

  let url = `${API_BASE_URL}${path}`;
  if (query) {
    const params = new URLSearchParams();
    Object.entries(query).forEach(([key, value]) => {
      if (value !== undefined && value !== null && value !== "") params.set(key, value);
    });
    const qs = params.toString();
    if (qs) url += `?${qs}`;
  }

  let response;
  try {
    response = await fetch(url, {
      method,
      headers,
      body: body ? JSON.stringify(body) : undefined,
    });
  } catch (networkErr) {
    throw new ApiError(
      `Could not reach the XYZ AI backend at ${API_BASE_URL}. Is it running (uvicorn app.main:app --reload --port 8000)?`,
      0
    );
  }

  let data = null;
  try {
    data = await response.json();
  } catch {
    // Some responses (rare) may not be JSON; fall through with data=null.
  }

  if (!response.ok) {
    // FastAPI's HTTPException(detail=...) is sometimes a plain string
    // (most errors) and sometimes a {message, options} object (the
    // ClarificationNeeded case from authz.py/tools.py, surfaced as a
    // 409 -- e.g. an ambiguous student name, or a teacher assigned to
    // multiple classes who needs to specify one).
    const detail = data?.detail;
    if (detail && typeof detail === "object") {
      throw new ApiError(detail.message || `Request to ${path} failed (${response.status}).`, response.status, detail.options);
    }
    throw new ApiError(detail || `Request to ${path} failed (${response.status}).`, response.status);
  }
  return data;
}

export const api = {
  health: () => request("/health"),

  // --- Auth -----------------------------------------------------------
  registerTeacher: (payload) => request("/auth/register/teacher", { method: "POST", body: payload }),
  registerStudent: (payload) => request("/auth/register/student", { method: "POST", body: payload }),
  registerParent: (payload) => request("/auth/register/parent", { method: "POST", body: payload }),
  registerPrincipal: (payload) => request("/auth/register/principal", { method: "POST", body: payload }),

  login: ({ role, identifier, password }) =>
    request("/auth/login", { method: "POST", body: { role, identifier, password } }),

  forgotPassword: ({ role, gmail, new_password, verify_new_password }) =>
    request("/auth/forgot-password", {
      method: "POST",
      body: { role, gmail, new_password, verify_new_password },
    }),

  // --- Chat -------------------------------------------------------------
  sendChatMessage: (token, message) =>
    request("/chat", { method: "POST", token, body: { message } }),

  resetChat: (token) => request("/chat/reset", { method: "POST", token }),

  myEscalations: (token) => request("/escalations/mine", { token }),

  languages: () => request("/languages"),

  // --- Flow C: interactive attendance grid (Teacher) ---------------------
  getClassAttendance: (token, { className, section, markDate }) =>
    request("/attendance/class", {
      token,
      query: { class_name: className, section, mark_date: markDate },
    }),

  saveClassAttendance: (token, { className, section, markDate, records }) =>
    request("/attendance/class", {
      method: "POST",
      token,
      body: { class_name: className, section, mark_date: markDate || null, records },
    }),

  // --- Flow D: interactive marks-entry grid (Teacher) ---------------------
  saveClassMarks: (token, { className, section, examType, records }) =>
    request("/marks/class", {
      method: "POST",
      token,
      body: { class_name: className, section, exam_type: examType, records },
    }),

  // --- Flow E: messaging / warnings ---------------------------------------
  sendWarning: (token, { targetStudentId, messageContent }) =>
    request("/communications/warning", {
      method: "POST",
      token,
      body: { target_student_id: targetStudentId, message_content: messageContent },
    }),

  askTeacher: (token, { targetTeacherId, messageContent, subject }) =>
    request("/communications/ask", {
      method: "POST",
      token,
      body: { target_teacher_id: targetTeacherId, message_content: messageContent, subject: subject || null },
    }),

  myCommunications: (token, { unreadOnly } = {}) =>
    request("/communications/mine", { token, query: { unread_only: unreadOnly ? "true" : undefined } }),

  // --- Flow F: principal dashboard ----------------------------------------
  // NOTE: these are reachable by more than just the principal role -- see
  // the module docstring above. A teacher fetching their own profile via
  // teacherProfile(token, own_teacher_id) is a normal, allowed call.
  teachersBySubject: (token, subject) =>
    request("/principal/teachers", { token, query: { subject } }),

  studentProfile: (token, studentId) =>
    request(`/principal/student/${encodeURIComponent(studentId)}`, { token }),

  teacherProfile: (token, teacherId) =>
    request(`/principal/teacher/${encodeURIComponent(teacherId)}`, { token }),

  summaryGrid: (token) => request("/principal/summary-grid", { token }),
};

export { ApiError, API_BASE_URL };
