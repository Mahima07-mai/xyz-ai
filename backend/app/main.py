"""
FastAPI entrypoint (Phase 3).

  GET  /health                    - liveness check, no auth
  GET  /llm-check                 - LLM API call smoke test
  GET  /languages                 - language catalog for the voice/language picker
  POST /auth/register/{role}      - registration for teacher|student|parent|principal
  POST /auth/login                - role-scoped login -> session token
  POST /auth/forgot-password      - gmail+role -> new password
  POST /chat                      - the core chat loop (all 4 roles)
  POST /chat/reset                - clears the caller's own conversation history
  GET  /escalations/mine          - caller's own escalation history

  # Flow C: interactive attendance grid (Teacher)
  GET  /attendance/class          - fetch a class/section/date grid to edit
  POST /attendance/class          - bulk save the grid

  # Flow D: interactive marks-entry grid (Teacher)
  POST /marks/class               - bulk save a class/section/exam_type grid

  # Flow E: messaging / warnings
  POST /communications/warning    - teacher -> student warning
  POST /communications/ask        - student/parent -> teacher doubt/query
  GET  /communications/mine       - teacher's own inbox

  # Flow F: principal dashboard
  GET  /principal/teachers        - teachers by subject_handled
  GET  /principal/student/{id}    - any student's bio profile
  GET  /principal/teacher/{id}    - any teacher's bio profile
  GET  /principal/summary-grid    - class/section counts + assigned teachers

Run with: uvicorn app.main:app --reload --port 8000
"""
from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy.orm import Session

from .auth import (
    ForgotPasswordRequest,
    LoginRequest,
    ParentRegisterRequest,
    PrincipalRegisterRequest,
    StudentRegisterRequest,
    TeacherRegisterRequest,
    forgot_password,
    get_current_user,
    login as auth_login,
    register_parent,
    register_principal,
    register_student,
    register_teacher,
)
from .authz import AuthorizationError, require_principal
from .database import Base, engine, get_db
from .escalation import list_own_escalations
from .language import language_catalog
from .llm_client import hello_world_check, run_chat_turn
from .model import AuthStudent, AuthTeacher
from .sessions import conversation_store
from .tools import (
    ToolError,
    get_class_attendance,
    get_my_communications,
    get_student_profile,
    get_teacher_profile,
    mark_attendance_bulk,
    submit_class_marks,
)
from .tools import ask_teacher as _ask_teacher
from .tools import lookup_teachers_by_subject as _lookup_teachers_by_subject
from .tools import send_warning as _send_warning

app = FastAPI(title="XYZ AI - Backend (Phase 3)")

# Wide-open CORS for local dev only. Tighten this to the real frontend
# origin before any real deployment.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def _create_tables_on_startup():
    """Create any tables that don't yet exist against the configured
    PostgreSQL database. `.model` is already imported above (directly and
    transitively), which registers every ORM class on `Base.metadata`
    before this runs, so a genuinely fresh database is fully usable
    without a separate manual `seed_data.py` run first."""
    Base.metadata.create_all(bind=engine)


def _tool_error_to_http(e: ToolError) -> HTTPException:
    if e.options:
        return HTTPException(status_code=409, detail={"message": e.message, "options": e.options})
    return HTTPException(status_code=403, detail=e.message)


def _authz_error_to_http(e: AuthorizationError) -> HTTPException:
    return HTTPException(status_code=403, detail=e.message)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/llm-check")
def llm_check():
    try:
        reply = hello_world_check()
        return {"status": "ok", "llm_reply": reply}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"LLM check failed: {e}")


@app.get("/languages")
def languages():
    """Single source of truth for supported vs. full-target languages plus
    BCP-47 locale tags. No auth required -- static capability info needed
    before login too. See app/language.py."""
    return {"languages": language_catalog()}


# ---------------------------------------------------------------------------
# Auth: registration / login / forgot-password
# ---------------------------------------------------------------------------

@app.post("/auth/register/teacher")
def register_teacher_endpoint(payload: TeacherRegisterRequest, db: Session = Depends(get_db)):
    teacher = register_teacher(db, payload)
    return {"teacher_id": teacher.teacher_id, "name": teacher.name}


@app.post("/auth/register/student")
def register_student_endpoint(payload: StudentRegisterRequest, db: Session = Depends(get_db)):
    student = register_student(db, payload)
    return {"student_id": student.student_id, "name": student.name}


@app.post("/auth/register/parent")
def register_parent_endpoint(payload: ParentRegisterRequest, db: Session = Depends(get_db)):
    parent = register_parent(db, payload)
    return {"parent_id": parent.parent_id, "name": parent.name}


@app.post("/auth/register/principal")
def register_principal_endpoint(payload: PrincipalRegisterRequest, db: Session = Depends(get_db)):
    principal = register_principal(db, payload)
    return {"principal_id": principal.principal_id, "name": principal.name}


@app.post("/auth/login")
def login_endpoint(payload: LoginRequest, db: Session = Depends(get_db)):
    token = auth_login(db, payload)
    return {"access_token": token, "token_type": "bearer"}


@app.post("/auth/forgot-password")
def forgot_password_endpoint(payload: ForgotPasswordRequest, db: Session = Depends(get_db)):
    forgot_password(db, payload)
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# Chat loop
# ---------------------------------------------------------------------------

class ChatRequest(BaseModel):
    message: str


@app.post("/chat")
def chat(
    payload: ChatRequest,
    caller: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    history = conversation_store.get(caller["id"])
    result = run_chat_turn(db, caller, history, payload.message)
    conversation_store.set(caller["id"], result["conversation_history"])
    return {"reply": result["reply"]}


@app.post("/chat/reset")
def reset_chat(caller: dict = Depends(get_current_user)):
    """Scoped to the verified caller's own id only -- there is no parameter
    that lets one user reset another user's session."""
    conversation_store.clear(caller["id"])
    return {"status": "ok"}


@app.get("/escalations/mine")
def my_escalations(caller: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    """Read-only history of the CALLER's OWN escalation requests. This is
    what proves the 'no false success claims' requirement: the assistant's
    chat claims and this endpoint's true status always read the same row."""
    return {"escalations": list_own_escalations(db, caller)}


# ---------------------------------------------------------------------------
# Flow C: interactive attendance grid (Teacher)
# ---------------------------------------------------------------------------

@app.get("/attendance/class")
def get_class_attendance_endpoint(
    class_name: str, section: str, mark_date: str | None = None,
    caller: dict = Depends(get_current_user), db: Session = Depends(get_db),
):
    try:
        return get_class_attendance(db, caller, class_name=class_name, section=section, mark_date=mark_date)
    except ToolError as e:
        raise _tool_error_to_http(e)


class AttendanceRow(BaseModel):
    student_id: str
    status: str  # "P" or "A"


class BulkAttendanceRequest(BaseModel):
    class_name: str
    section: str
    mark_date: str | None = None
    records: list[AttendanceRow]


@app.post("/attendance/class")
def save_class_attendance_endpoint(
    payload: BulkAttendanceRequest,
    caller: dict = Depends(get_current_user), db: Session = Depends(get_db),
):
    try:
        return mark_attendance_bulk(
            db, caller, class_name=payload.class_name, section=payload.section,
            records=[r.model_dump() for r in payload.records], mark_date=payload.mark_date,
        )
    except ToolError as e:
        raise _tool_error_to_http(e)


# ---------------------------------------------------------------------------
# Flow D: interactive marks-entry grid (Teacher)
# ---------------------------------------------------------------------------

class BulkMarksRequest(BaseModel):
    class_name: str
    section: str
    exam_type: str
    # Each record: {"student_id": "...", "Maths": 78, "Science": 82, ...}
    records: list[dict]


@app.post("/marks/class")
def save_class_marks_endpoint(
    payload: BulkMarksRequest,
    caller: dict = Depends(get_current_user), db: Session = Depends(get_db),
):
    try:
        return submit_class_marks(
            db, caller, class_name=payload.class_name, section=payload.section,
            exam_type=payload.exam_type, records=payload.records,
        )
    except ToolError as e:
        raise _tool_error_to_http(e)


# ---------------------------------------------------------------------------
# Flow E: messaging / warnings
# ---------------------------------------------------------------------------

class WarningRequest(BaseModel):
    target_student_id: str
    message_content: str


@app.post("/communications/warning")
def send_warning_endpoint(
    payload: WarningRequest,
    caller: dict = Depends(get_current_user), db: Session = Depends(get_db),
):
    try:
        return _send_warning(db, caller, target_student_id=payload.target_student_id,
                              message_content=payload.message_content)
    except ToolError as e:
        raise _tool_error_to_http(e)


class AskTeacherRequest(BaseModel):
    target_teacher_id: str
    message_content: str
    subject: str | None = None


@app.post("/communications/ask")
def ask_teacher_endpoint(
    payload: AskTeacherRequest,
    caller: dict = Depends(get_current_user), db: Session = Depends(get_db),
):
    try:
        return _ask_teacher(
            db, caller, target_teacher_id=payload.target_teacher_id,
            message_content=payload.message_content, subject=payload.subject,
        )
    except ToolError as e:
        raise _tool_error_to_http(e)


@app.get("/communications/mine")
def my_communications_endpoint(
    unread_only: bool = False,
    caller: dict = Depends(get_current_user), db: Session = Depends(get_db),
):
    try:
        return get_my_communications(db, caller, unread_only=unread_only)
    except ToolError as e:
        raise _tool_error_to_http(e)


# ---------------------------------------------------------------------------
# Flow F: principal dashboard
# ---------------------------------------------------------------------------

@app.get("/principal/teachers")
def principal_teachers_by_subject(
    subject: str, caller: dict = Depends(get_current_user), db: Session = Depends(get_db),
):
    try:
        return _lookup_teachers_by_subject(db, caller, subject=subject)
    except ToolError as e:
        raise _tool_error_to_http(e)


@app.get("/principal/student/{student_id}")
def principal_student_profile(
    student_id: str, caller: dict = Depends(get_current_user), db: Session = Depends(get_db),
):
    try:
        return get_student_profile(db, caller, student_id=student_id)
    except ToolError as e:
        raise _tool_error_to_http(e)


@app.get("/principal/teacher/{teacher_id}")
def principal_teacher_profile(
    teacher_id: str, caller: dict = Depends(get_current_user), db: Session = Depends(get_db),
):
    try:
        return get_teacher_profile(db, caller, teacher_id=teacher_id)
    except ToolError as e:
        raise _tool_error_to_http(e)


@app.get("/principal/summary-grid")
def principal_summary_grid(caller: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    """Class/section grid: student counts + assigned teachers per
    class-section, for the Principal Dashboard summary board. Principal
    role only -- this is a school-wide view, deliberately not exposed to
    any other role."""
    try:
        require_principal(caller)
    except AuthorizationError as e:
        raise _authz_error_to_http(e)

    students = db.query(AuthStudent).all()
    teachers = db.query(AuthTeacher).all()

    grid: dict[str, dict] = {}
    for s in students:
        key = f"{s.class_name}-{s.section}"
        grid.setdefault(key, {"class_name": s.class_name, "section": s.section,
                               "student_count": 0, "teachers": []})
        grid[key]["student_count"] += 1

    for t in teachers:
        for c in (t.classes or []):
            for sec in (t.sections or []):
                key = f"{c}-{sec}"
                if key in grid:
                    grid[key]["teachers"].append({"teacher_id": t.teacher_id, "name": t.name,
                                                   "subject_handled": t.subject_handled})

    return {"grid": list(grid.values())}