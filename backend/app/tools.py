"""
The Tool / Workflow layer (Phase 3, extended in Phase 4 with the AI
analytics tools get_subject_performance_insights and
get_attendance_patterns below, which back the directive's pedagogical-
suggestion and absenteeism-pattern report requirements). Both new tools
follow the same rule as everything else in this file: they return real,
verified numbers only. Any "AI-generated" narrative on top of those
numbers is produced by the persona-driven chat loop in llm_client.py
reasoning over the tool result, never invented inside the tool itself.

Two kinds of entry points live here:

1. LLM-callable tools (TOOL_SCHEMAS / TOOL_HANDLERS / run_tool) -- what the
   chat engine (llm_client.py) can invoke. Every handler re-verifies the
   caller's VERIFIED role/scope via authz.py before touching any data --
   the LLM is never trusted to have decided access on its own.

2. Plain functions used directly by REST endpoints in main.py for the
   *interactive* UI flows (attendance grid, marks entry grid) described in
   the directive's Flow C/D -- these are structured form submissions, not
   natural-language chat, so they don't need an LLM tool schema, but they
   go through the exact same authz.py checks and the same audit logging as
   everything else. There is no code path anywhere in this file that
   touches daily_attendance / exam_marks / teacher_communications / bio
   tables without first calling an authz.verify_* / resolve_* guard.

Every function takes `caller: dict` -- {"id", "role", "name"} from
auth.get_current_user() -- and never a role/id typed in chat text.
"""
from datetime import date

from sqlalchemy.orm import Session

from .authz import (
    AuthorizationError,
    ClarificationNeeded,
    get_authenticated_teacher,
    require_role,
    resolve_linked_child,
    resolve_own_student,
    resolve_student_in_class,
    verify_attendance_access,
    verify_marks_access,
    verify_principal_access,
    verify_report_scope,
    verify_student_bio_access,
    verify_teacher_access,
    verify_teacher_bio_access,
    verify_teacher_communication_access,
    verify_warning_access,
)
from .escalation import request_escalation as _request_escalation
from .model import (
    AuditLog,
    AuthStudent,
    AuthTeacher,
    DailyAttendance,
    ExamMarks,
    OverallAttendance,
    OverallGrading,
    StudentBio,
    TeacherBio,
    TeacherCommunication,
    compute_grade,
)


class ToolError(Exception):
    """Raised for any denied, invalid, or clarification-needed tool call.
    The orchestrator (llm_client.py) turns this into a natural-language
    explanation -- the LLM never decides access itself, it only gets told
    the outcome after the fact."""
    def __init__(self, message: str, options: list[str] | None = None):
        self.message = message
        self.options = options  # populated only when clarification is needed
        super().__init__(message)


# Maps the human subject name to the exam_marks column that stores it.
SUBJECT_COLUMNS = {
    "Maths": "maths_mark",
    "Science": "science_mark",
    "Language": "language_mark",
    "Social": "social_mark",
    "Technology": "technology_mark",
}
EXAM_TYPES = {"term1", "term2", "term3", "final"}


# ---------------------------------------------------------------------------
# Audit helpers
# ---------------------------------------------------------------------------

def _log(db: Session, caller: dict, tool_name: str, target: str | None,
         allowed: bool, detail: str | None = None) -> None:
    db.add(AuditLog(
        actor_id=str(caller["id"]),
        actor_role=caller["role"],
        tool_name=tool_name,
        target_description=target,
        allowed=allowed,
        detail=detail,
    ))
    db.commit()


def _to_tool_error(db: Session, caller: dict, tool_name: str, target: str | None, e: AuthorizationError) -> ToolError:
    _log(db, caller, tool_name, target, False, detail=e.message)
    if isinstance(e, ClarificationNeeded):
        return ToolError(e.message, options=e.options)
    return ToolError(e.message)


# ---------------------------------------------------------------------------
# Attendance: reads
# ---------------------------------------------------------------------------

def _attendance_payload(name: str, records: list[DailyAttendance]) -> dict:
    if not records:
        return {"student_name": name, "records": [], "message": "No attendance data found yet."}
    return {
        "student_name": name,
        "records": [{"date": r.date.isoformat(), "status": r.status} for r in records],
    }


def get_own_attendance(db: Session, caller: dict, days: int = 30, **_ignored) -> dict:
    """Tool: get_own_attendance -- Student role only, own record only."""
    try:
        verify_attendance_access(db, caller)
        student = resolve_own_student(db, caller)
    except AuthorizationError as e:
        raise _to_tool_error(db, caller, "get_own_attendance", "self", e)

    records = (
        db.query(DailyAttendance)
        .filter(DailyAttendance.student_id == student.student_id)
        .order_by(DailyAttendance.date.desc())
        .limit(days)
        .all()
    )
    _log(db, caller, "get_own_attendance", f"student_id={student.student_id}", True,
         detail=f"Returned {len(records)} record(s).")
    return _attendance_payload(student.name, records)


def get_child_attendance(db: Session, caller: dict, days: int = 30,
                          child_name: str | None = None, **_ignored) -> dict:
    """Tool: get_child_attendance -- Parent role only, linked child only."""
    try:
        verify_attendance_access(db, caller)
        student = resolve_linked_child(db, caller, child_name)
    except AuthorizationError as e:
        raise _to_tool_error(db, caller, "get_child_attendance", child_name, e)

    records = (
        db.query(DailyAttendance)
        .filter(DailyAttendance.student_id == student.student_id)
        .order_by(DailyAttendance.date.desc())
        .limit(days)
        .all()
    )
    _log(db, caller, "get_child_attendance", f"student_id={student.student_id}", True,
         detail=f"Returned {len(records)} record(s).")
    return _attendance_payload(student.name, records)


def get_class_attendance(db: Session, caller: dict, class_name: str, section: str,
                          mark_date: str | None = None, **_ignored) -> dict:
    """Backs the Flow C interactive attendance grid: a teacher opens their
    own assigned class/section for a given date and gets every student in
    it plus that student's existing status (or None if not yet marked),
    so the frontend can pre-fill the P/A toggle table."""
    try:
        teacher = verify_teacher_access(db, caller, class_name=class_name, section=section)
    except AuthorizationError as e:
        raise _to_tool_error(db, caller, "get_class_attendance", f"{class_name}{section}", e)

    try:
        record_date = date.fromisoformat(mark_date) if mark_date else date.today()
    except ValueError:
        raise ToolError(f"'{mark_date}' is not a valid date. Use YYYY-MM-DD.")

    students = (
        db.query(AuthStudent)
        .filter(AuthStudent.class_name == class_name, AuthStudent.section == section)
        .order_by(AuthStudent.name)
        .all()
    )
    existing = {
        r.student_id: r.status
        for r in db.query(DailyAttendance).filter(
            DailyAttendance.class_name == class_name,
            DailyAttendance.section == section,
            DailyAttendance.date == record_date,
        )
    }

    _log(db, caller, "get_class_attendance", f"{class_name}{section} date={record_date}", True,
         detail=f"{len(students)} student(s) in scope.")

    return {
        "class_name": class_name,
        "section": section,
        "date": record_date.isoformat(),
        "students": [
            {"student_id": s.student_id, "name": s.name, "status": existing.get(s.student_id, "P")}
            for s in students
        ],
    }


# ---------------------------------------------------------------------------
# Attendance: writes
# ---------------------------------------------------------------------------

def _recompute_overall_attendance(db: Session, student_id: str) -> None:
    rows = db.query(DailyAttendance).filter(DailyAttendance.student_id == student_id).all()
    present = sum(1 for r in rows if r.status == "P")
    absent = sum(1 for r in rows if r.status == "A")
    total = present + absent
    pct = round((present / total) * 100, 2) if total else 0.0

    overall = db.query(OverallAttendance).filter(OverallAttendance.student_id == student_id).first()
    if overall is None:
        overall = OverallAttendance(student_id=student_id)
        db.add(overall)
    overall.total_present_days = present
    overall.total_absent_days = absent
    overall.total_working_days = total
    overall.attendance_percentage = pct
    db.commit()


def _upsert_attendance(db: Session, class_name: str, section: str, student_id: str,
                        status: str, record_date: date) -> str:
    status = status.strip().upper()
    if status not in ("P", "A"):
        raise ToolError(f"'{status}' is not a valid attendance status. Use P (present) or A (absent).")

    existing = (
        db.query(DailyAttendance)
        .filter(DailyAttendance.student_id == student_id, DailyAttendance.date == record_date)
        .first()
    )
    if existing:
        existing.status = status
        action = "updated"
    else:
        db.add(DailyAttendance(
            date=record_date, class_name=class_name, section=section,
            student_id=student_id, status=status,
        ))
        action = "created"
    db.commit()
    _recompute_overall_attendance(db, student_id)
    return action


def mark_attendance(db: Session, caller: dict, student_name: str, status: str,
                     class_name: str, section: str, mark_date: str | None = None, **_ignored) -> dict:
    """Tool: mark_attendance -- Teacher role only, own assigned class/section
    only. Single-student convenience path for chat ("mark Rahul absent
    today") -- the interactive grid uses mark_attendance_bulk instead."""
    try:
        student = resolve_student_in_class(db, caller, student_name, class_name=class_name, section=section)
        verify_attendance_access(db, caller, student_id=student.student_id, write=True)
    except AuthorizationError as e:
        raise _to_tool_error(db, caller, "mark_attendance", student_name, e)

    try:
        record_date = date.fromisoformat(mark_date) if mark_date else date.today()
    except ValueError:
        raise ToolError(f"'{mark_date}' is not a valid date. Use YYYY-MM-DD.")

    action = _upsert_attendance(db, class_name, section, student.student_id, status, record_date)

    _log(db, caller, "mark_attendance", f"student_id={student.student_id} date={record_date}", True,
         detail=f"{action} as {status.strip().upper()}")

    return {
        "student_name": student.name, "date": record_date.isoformat(),
        "status": status.strip().upper(), "action": action,
    }


def mark_attendance_bulk(db: Session, caller: dict, class_name: str, section: str,
                          records: list[dict], mark_date: str | None = None) -> dict:
    """Backs the Flow C interactive attendance grid's Save action. `records`
    is [{"student_id": ..., "status": "P"|"A"}, ...]. Every student_id is
    re-validated against the teacher's authorized class/section -- a
    tampered student_id in the payload cannot write outside that scope."""
    try:
        teacher = verify_teacher_access(db, caller, class_name=class_name, section=section)
    except AuthorizationError as e:
        raise _to_tool_error(db, caller, "mark_attendance_bulk", f"{class_name}{section}", e)

    try:
        record_date = date.fromisoformat(mark_date) if mark_date else date.today()
    except ValueError:
        raise ToolError(f"'{mark_date}' is not a valid date. Use YYYY-MM-DD.")

    valid_ids = {
        s.student_id for s in db.query(AuthStudent).filter(
            AuthStudent.class_name == class_name, AuthStudent.section == section,
        )
    }

    results = []
    for row in records:
        student_id = str(row.get("student_id", "")).strip()
        status = str(row.get("status", "")).strip()
        if student_id not in valid_ids:
            results.append({"student_id": student_id, "error": "Not in this class/section; skipped."})
            continue
        try:
            action = _upsert_attendance(db, class_name, section, student_id, status, record_date)
            results.append({"student_id": student_id, "status": status.upper(), "action": action})
        except ToolError as e:
            results.append({"student_id": student_id, "error": e.message})

    saved = sum(1 for r in results if "action" in r)
    _log(db, caller, "mark_attendance_bulk", f"{class_name}{section} date={record_date}", True,
         detail=f"Saved {saved}/{len(records)} record(s).")

    return {"class_name": class_name, "section": section, "date": record_date.isoformat(), "results": results}


# ---------------------------------------------------------------------------
# Marks: writes / grading
# ---------------------------------------------------------------------------

def _recompute_marks_row(row: ExamMarks) -> None:
    values = [
        row.maths_mark, row.science_mark, row.language_mark,
        row.social_mark, row.technology_mark,
    ]
    present = [v for v in values if v is not None]
    if not present:
        row.total_marks = None
        row.average_marks = None
        row.grade = None
        return
    total = sum(present)
    average = total / len(present)
    row.total_marks = round(total, 2)
    row.average_marks = round(average, 2)
    row.grade = compute_grade(average)


def _maybe_update_overall_grading(db: Session, student_id: str) -> None:
    """Only creates/updates OverallGrading once term1, term2, term3, AND
    final all exist with a computed average -- per the directive's
    'condition' on overall_grading."""
    rows = {
        r.exam_type: r
        for r in db.query(ExamMarks).filter(ExamMarks.student_id == student_id)
    }
    required = ("term1", "term2", "term3", "final")
    if not all(t in rows and rows[t].average_marks is not None for t in required):
        return

    term_avg = sum(rows[t].average_marks for t in ("term1", "term2", "term3")) / 3
    term_weighted = round(term_avg * 0.5, 2)          # scaled to /50
    final_weighted = round(rows["final"].average_marks * 0.5, 2)  # scaled to /50
    final_total = round(term_weighted + final_weighted, 2)        # out of 100

    grading = db.query(OverallGrading).filter(OverallGrading.student_id == student_id).first()
    if grading is None:
        grading = OverallGrading(student_id=student_id)
        db.add(grading)
    grading.term_average_weighted = term_weighted
    grading.final_exam_weighted = final_weighted
    grading.final_total_mark = final_total
    grading.final_overall_grade = compute_grade(final_total)
    db.commit()

    bio = db.query(StudentBio).filter(StudentBio.student_id == student_id).first()
    if bio is not None:
        bio.overall_average_score = final_total
        db.commit()


def submit_exam_marks(db: Session, caller: dict, student_name: str, exam_type: str,
                       class_name: str, section: str, marks: dict, **_ignored) -> dict:
    """Tool: submit_exam_marks -- Teacher role only, own assigned
    class/section, and only for subject(s) the teacher actually handles.
    `marks` is {"Maths": 78, "Science": 82, ...} -- any subset of the 5
    allowed subjects; a teacher who only teaches Science cannot slip Maths
    marks in through this call even for their own assigned class."""
    exam_type = (exam_type or "").strip().lower()
    if exam_type not in EXAM_TYPES:
        raise ToolError(f"'{exam_type}' is not a valid exam type. Use term1, term2, term3, or final.")

    unknown_subjects = sorted(set(marks) - set(SUBJECT_COLUMNS))
    if unknown_subjects:
        raise ToolError(f"Unknown subject(s): {', '.join(unknown_subjects)}.")

    try:
        student = resolve_student_in_class(db, caller, student_name, class_name=class_name, section=section)
        for subject in marks:
            verify_marks_access(db, caller, student_id=student.student_id, subject=subject, write=True)
    except AuthorizationError as e:
        raise _to_tool_error(db, caller, "submit_exam_marks", student_name, e)

    for value in marks.values():
        if not isinstance(value, (int, float)) or not (0 <= value <= 100):
            raise ToolError("Each mark must be a number between 0 and 100.")

    row = (
        db.query(ExamMarks)
        .filter(ExamMarks.student_id == student.student_id, ExamMarks.exam_type == exam_type)
        .first()
    )
    if row is None:
        row = ExamMarks(
            student_id=student.student_id, class_name=class_name,
            section=section, exam_type=exam_type,
        )
        db.add(row)

    for subject, value in marks.items():
        setattr(row, SUBJECT_COLUMNS[subject], float(value))

    _recompute_marks_row(row)
    db.commit()
    _maybe_update_overall_grading(db, student.student_id)

    _log(db, caller, "submit_exam_marks", f"student_id={student.student_id} exam={exam_type}", True,
         detail=f"Subjects updated: {', '.join(marks)}")

    return {
        "student_name": student.name, "exam_type": exam_type,
        "total_marks": row.total_marks, "average_marks": row.average_marks, "grade": row.grade,
    }


def submit_class_marks(db: Session, caller: dict, class_name: str, section: str,
                        exam_type: str, records: list[dict]) -> dict:
    """Backs the Flow D interactive marks-entry grid's Save action.
    `records` is [{"student_id": ..., "Maths": 78, "Science": 82, ...}, ...].
    Same per-subject teacher scoping as submit_exam_marks, applied row by
    row so a teacher can only ever save marks for subjects they handle."""
    exam_type = (exam_type or "").strip().lower()
    if exam_type not in EXAM_TYPES:
        raise ToolError(f"'{exam_type}' is not a valid exam type. Use term1, term2, term3, or final.")

    try:
        teacher = verify_teacher_access(db, caller, class_name=class_name, section=section)
    except AuthorizationError as e:
        raise _to_tool_error(db, caller, "submit_class_marks", f"{class_name}{section}", e)

    handled_subjects = {
        s for s in SUBJECT_COLUMNS
        if _normalize_subject(teacher, s)
    }

    valid_ids = {
        s.student_id for s in db.query(AuthStudent).filter(
            AuthStudent.class_name == class_name, AuthStudent.section == section,
        )
    }

    results = []
    for entry in records:
        student_id = str(entry.get("student_id", "")).strip()
        if student_id not in valid_ids:
            results.append({"student_id": student_id, "error": "Not in this class/section; skipped."})
            continue

        subject_values = {k: v for k, v in entry.items() if k in SUBJECT_COLUMNS}
        disallowed = set(subject_values) - handled_subjects
        if disallowed:
            results.append({
                "student_id": student_id,
                "error": f"Not authorized for: {', '.join(sorted(disallowed))}; those columns skipped.",
            })
            subject_values = {k: v for k, v in subject_values.items() if k in handled_subjects}
        if not subject_values:
            continue

        row = (
            db.query(ExamMarks)
            .filter(ExamMarks.student_id == student_id, ExamMarks.exam_type == exam_type)
            .first()
        )
        if row is None:
            row = ExamMarks(student_id=student_id, class_name=class_name, section=section, exam_type=exam_type)
            db.add(row)
        for subject, value in subject_values.items():
            row_value = getattr(row, SUBJECT_COLUMNS[subject])
            setattr(row, SUBJECT_COLUMNS[subject], float(value))
        _recompute_marks_row(row)
        db.commit()
        _maybe_update_overall_grading(db, student_id)
        results.append({"student_id": student_id, "total": row.total_marks, "average": row.average_marks, "grade": row.grade})

    saved = sum(1 for r in results if "total" in r)
    _log(db, caller, "submit_class_marks", f"{class_name}{section} exam={exam_type}", True,
         detail=f"Saved {saved}/{len(records)} record(s).")

    return {"class_name": class_name, "section": section, "exam_type": exam_type, "results": results}


def _normalize_subject(teacher: AuthTeacher, subject: str) -> bool:
    handled = teacher.subject_handled or []
    return subject.strip().casefold() in {str(s).strip().casefold() for s in handled}


# ---------------------------------------------------------------------------
# Marks: reads
# ---------------------------------------------------------------------------

def _marks_payload(name: str, rows: list[ExamMarks]) -> dict:
    if not rows:
        return {"student_name": name, "exams": [], "message": "No marks recorded yet."}
    return {
        "student_name": name,
        "exams": [
            {
                "exam_type": r.exam_type,
                "maths": r.maths_mark, "science": r.science_mark, "language": r.language_mark,
                "social": r.social_mark, "technology": r.technology_mark,
                "total": r.total_marks, "average": r.average_marks, "grade": r.grade,
            }
            for r in rows
        ],
    }


def get_own_marks(db: Session, caller: dict, **_ignored) -> dict:
    """Tool: get_own_marks -- Student role only, own marks only."""
    try:
        verify_marks_access(db, caller)
        student = resolve_own_student(db, caller)
    except AuthorizationError as e:
        raise _to_tool_error(db, caller, "get_own_marks", "self", e)

    rows = db.query(ExamMarks).filter(ExamMarks.student_id == student.student_id).all()
    _log(db, caller, "get_own_marks", f"student_id={student.student_id}", True)
    return _marks_payload(student.name, rows)


def get_child_marks(db: Session, caller: dict, child_name: str | None = None, **_ignored) -> dict:
    """Tool: get_child_marks -- Parent role only, linked child only."""
    try:
        verify_marks_access(db, caller)
        student = resolve_linked_child(db, caller, child_name)
    except AuthorizationError as e:
        raise _to_tool_error(db, caller, "get_child_marks", child_name, e)

    rows = db.query(ExamMarks).filter(ExamMarks.student_id == student.student_id).all()
    _log(db, caller, "get_child_marks", f"student_id={student.student_id}", True)
    return _marks_payload(student.name, rows)


def get_class_failure_report(db: Session, caller: dict, class_name: str, section: str,
                              subject: str, exam_type: str | None = None, **_ignored) -> dict:
    """Tool: get_class_failure_report -- Teacher (own class + own subject)
    or Principal (any class/subject). Answers Flow E's 'how many students
    failed in my subject' by scoping the student set through authz.py
    first, then filtering that exact set's marks -- never a raw class-wide
    query that could leak a student outside the caller's authorized scope."""
    if subject not in SUBJECT_COLUMNS:
        raise ToolError(f"'{subject}' is not a recognized subject.")

    try:
        student_ids = verify_report_scope(db, caller, class_name=class_name, section=section, subject=subject)
    except AuthorizationError as e:
        raise _to_tool_error(db, caller, "get_class_failure_report", f"{class_name}{section}/{subject}", e)

    column = SUBJECT_COLUMNS[subject]
    query = db.query(ExamMarks).filter(ExamMarks.student_id.in_(student_ids))
    if exam_type:
        exam_type = exam_type.strip().lower()
        if exam_type not in EXAM_TYPES:
            raise ToolError(f"'{exam_type}' is not a valid exam type.")
        query = query.filter(ExamMarks.exam_type == exam_type)

    rows = [r for r in query.all() if getattr(r, column) is not None]
    failing = [r for r in rows if getattr(r, column) < 40]

    id_to_name = {
        s.student_id: s.name
        for s in db.query(AuthStudent).filter(AuthStudent.student_id.in_(student_ids))
    }

    _log(db, caller, "get_class_failure_report", f"{class_name}{section}/{subject}", True,
         detail=f"{len(failing)}/{len(rows)} failing")

    return {
        "class_name": class_name, "section": section, "subject": subject,
        "exam_type": exam_type or "all recorded exams",
        "total_students_with_marks": len(rows),
        "failing_count": len(failing),
        "failing_students": [
            {"student_id": r.student_id, "name": id_to_name.get(r.student_id, r.student_id),
             "mark": getattr(r, column), "exam_type": r.exam_type}
            for r in failing
        ],
    }


# ---------------------------------------------------------------------------
# AI analytics: pedagogical / teaching-improvement insights
# ---------------------------------------------------------------------------

# Score-band buckets used for the distribution the model reasons over.
# Kept coarse and few in number on purpose -- this is meant to describe a
# *shape* (a right-skewed class, a bimodal class, etc.), not to leak an
# effectively-individual data point through a narrow bucket.
_SCORE_BANDS = [
    ("0-39 (F)", 0, 40),
    ("40-59 (D/C)", 40, 60),
    ("60-79 (B/A)", 60, 80),
    ("80-100 (A+/S)", 80, 101),
]


def get_subject_performance_insights(db: Session, caller: dict, class_name: str, section: str,
                                      subject: str, exam_type: str | None = None, **_ignored) -> dict:
    """Tool: get_subject_performance_insights -- Teacher (own class/section
    AND own handled subject) or Principal (any). Teacher/Principal only --
    this is a class-performance-shape tool, not an individual bio lookup,
    so student/parent are never in scope here.

    Answers the directive's 'How can I improve the understanding of my
    students who scored low in Science?' by returning a real score
    distribution, an average, and the actual struggling students (name +
    mark) -- never an invented trend. The persona then synthesizes teaching
    strategies / remedial suggestions from these numbers; this tool
    deliberately does NOT generate prose itself, so a hallucinated
    statistic can never enter the data layer.
    """
    require_role(caller, "teacher", "principal")

    if subject not in SUBJECT_COLUMNS:
        raise ToolError(f"'{subject}' is not a recognized subject.")

    try:
        student_ids = verify_report_scope(db, caller, class_name=class_name, section=section, subject=subject)
    except AuthorizationError as e:
        raise _to_tool_error(db, caller, "get_subject_performance_insights", f"{class_name}{section}/{subject}", e)

    column = SUBJECT_COLUMNS[subject]
    query = db.query(ExamMarks).filter(ExamMarks.student_id.in_(student_ids))
    if exam_type:
        exam_type = exam_type.strip().lower()
        if exam_type not in EXAM_TYPES:
            raise ToolError(f"'{exam_type}' is not a valid exam type.")
        query = query.filter(ExamMarks.exam_type == exam_type)

    rows = [r for r in query.all() if getattr(r, column) is not None]

    _log(db, caller, "get_subject_performance_insights", f"{class_name}{section}/{subject}", True,
         detail=f"{len(rows)} scored record(s).")

    if not rows:
        return {
            "class_name": class_name, "section": section, "subject": subject,
            "exam_type": exam_type or "all recorded exams",
            "message": "No marks recorded yet for this subject in this scope.",
        }

    id_to_name = {
        s.student_id: s.name
        for s in db.query(AuthStudent).filter(AuthStudent.student_id.in_(student_ids))
    }

    scores = [getattr(r, column) for r in rows]
    average = round(sum(scores) / len(scores), 2)

    distribution = []
    for label, low, high in _SCORE_BANDS:
        count = sum(1 for s in scores if low <= s < high)
        distribution.append({"band": label, "count": count})

    # "struggling" = below 50, capped so the payload stays a shape summary
    # rather than a full roster dump.
    struggling = sorted(
        (
            {"student_id": r.student_id, "name": id_to_name.get(r.student_id, r.student_id),
             "mark": getattr(r, column), "exam_type": r.exam_type}
            for r in rows if getattr(r, column) < 50
        ),
        key=lambda item: item["mark"],
    )[:15]

    return {
        "class_name": class_name, "section": section, "subject": subject,
        "exam_type": exam_type or "all recorded exams",
        "students_with_marks": len(rows),
        "class_average": average,
        "highest": max(scores), "lowest": min(scores),
        "score_distribution": distribution,
        "struggling_students": struggling,
        "struggling_count": len(struggling),
    }


# ---------------------------------------------------------------------------
# AI analytics: absenteeism pattern analysis
# ---------------------------------------------------------------------------

_WEEKDAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


def get_attendance_patterns(db: Session, caller: dict, class_name: str, section: str,
                             days: int = 30, **_ignored) -> dict:
    """Tool: get_attendance_patterns -- Teacher (own class/section) or
    Principal (any). Teacher/Principal only, same reasoning as
    get_subject_performance_insights.

    Answers the directive's 'Give me the pattern of absentees for Section
    B. What percentage of students are regularly absent?' by returning the
    real day-of-week absence breakdown (peak absence days), the actual
    below-75%-attendance students, and the real overall percentage --
    never a synthesized guess. The persona narrates the pattern from these
    numbers only.
    """
    require_role(caller, "teacher", "principal")

    try:
        student_ids = verify_report_scope(db, caller, class_name=class_name, section=section)
    except AuthorizationError as e:
        raise _to_tool_error(db, caller, "get_attendance_patterns", f"{class_name}{section}", e)

    if not student_ids:
        _log(db, caller, "get_attendance_patterns", f"{class_name}{section}", True, detail="No students in scope.")
        return {"class_name": class_name, "section": section, "message": "No students found in this class/section."}

    records = (
        db.query(DailyAttendance)
        .filter(DailyAttendance.student_id.in_(student_ids))
        .order_by(DailyAttendance.date.desc())
        .limit(max(days, 1) * max(len(student_ids), 1))
        .all()
    )

    _log(db, caller, "get_attendance_patterns", f"{class_name}{section}", True, detail=f"{len(records)} record(s).")

    if not records:
        return {"class_name": class_name, "section": section, "message": "No attendance data found yet."}

    id_to_name = {
        s.student_id: s.name
        for s in db.query(AuthStudent).filter(AuthStudent.student_id.in_(student_ids))
    }

    total_present = sum(1 for r in records if r.status == "P")
    total_absent = sum(1 for r in records if r.status == "A")
    total = total_present + total_absent
    overall_pct = round((total_present / total) * 100, 2) if total else 0.0

    absences_by_weekday = {name: 0 for name in _WEEKDAY_NAMES}
    for r in records:
        if r.status == "A":
            absences_by_weekday[_WEEKDAY_NAMES[r.date.weekday()]] += 1

    peak_days = sorted(
        ({"day": day, "absences": count} for day, count in absences_by_weekday.items() if count > 0),
        key=lambda item: item["absences"], reverse=True,
    )

    below_75 = sorted(
        (
            {"student_id": o.student_id, "name": id_to_name.get(o.student_id, o.student_id),
             "percentage": o.attendance_percentage}
            for o in db.query(OverallAttendance).filter(
                OverallAttendance.student_id.in_(student_ids),
                OverallAttendance.attendance_percentage < 75,
            )
        ),
        key=lambda item: item["percentage"],
    )

    return {
        "class_name": class_name, "section": section,
        "records_considered": len(records),
        "overall_attendance_percentage": overall_pct,
        "absences_by_weekday": absences_by_weekday,
        "peak_absence_days": peak_days,
        "regularly_absent_students": below_75,
        "regularly_absent_count": len(below_75),
        "total_students_in_scope": len(student_ids),
    }


# ---------------------------------------------------------------------------
# Flow E: natural-language threshold filtering
# ---------------------------------------------------------------------------

_FILTER_OPERATORS = {
    "<": lambda value, threshold: value < threshold,
    ">": lambda value, threshold: value > threshold,
    "<=": lambda value, threshold: value <= threshold,
    ">=": lambda value, threshold: value >= threshold,
    "==": lambda value, threshold: value == threshold,
}


def filter_students_by_criteria(
    db: Session,
    caller: dict,
    metric: str,
    operator: str,
    threshold: float,
    class_name: str,
    section: str,
    subject: str | None = None,
    exam_type: str | None = None,
    **_ignored,
) -> dict:
    """Tool: filter_students_by_criteria -- Teacher (own class + section) or
    Principal (any). Answers the directive's Flow E natural-language
    threshold filtering requirement directly: "Show students with
    attendance < 40%", "Show students with marks > 90 in Term 1", "Show
    students who failed (< 40)".

    Scoped through the exact same verify_report_scope() boundary as
    get_class_failure_report / get_subject_performance_insights /
    get_attendance_patterns, so an LLM-composed filter can never reach a
    student outside the caller's authorized class/section (or, for a
    teacher, an unhandled subject). Returns the real matching students
    (id, name, and the actual metric value) straight from the DB -- never
    a synthesized or guessed list.

    metric:
        "attendance_percentage" -- OverallAttendance.attendance_percentage.
        "marks" -- ExamMarks. If `subject` is given, compares that
            subject's column (e.g. Science -> science_mark). If `subject`
            is omitted, compares the per-exam average_marks column
            instead, which is what a generic "who failed" (no subject
            named) question means.
    operator: one of "<", ">", "<=", ">=", "==".
    threshold: the numeric cutoff, e.g. 40 for "< 40%".
    exam_type: optional; restricts marks comparisons to one exam
        (term1/term2/term3/final). Ignored for the attendance metric.
    """
    require_role(caller, "teacher", "principal")

    if metric not in ("attendance_percentage", "marks"):
        raise ToolError(f"'{metric}' is not a recognized metric. Use 'attendance_percentage' or 'marks'.")

    if operator not in _FILTER_OPERATORS:
        raise ToolError(f"'{operator}' is not a recognized comparison operator.")

    if subject is not None and subject not in SUBJECT_COLUMNS:
        raise ToolError(f"'{subject}' is not a recognized subject.")

    if exam_type is not None:
        exam_type = exam_type.strip().lower()
        if exam_type not in EXAM_TYPES:
            raise ToolError(f"'{exam_type}' is not a valid exam type.")

    target = f"{class_name}{section}" + (f"/{subject}" if subject else "")

    try:
        student_ids = verify_report_scope(
            db, caller, class_name=class_name, section=section, subject=subject,
        )
    except AuthorizationError as e:
        raise _to_tool_error(db, caller, "filter_students_by_criteria", target, e)

    compare = _FILTER_OPERATORS[operator]

    id_to_name = {
        s.student_id: s.name
        for s in db.query(AuthStudent).filter(AuthStudent.student_id.in_(student_ids))
    }

    if metric == "attendance_percentage":
        rows = (
            db.query(OverallAttendance)
            .filter(OverallAttendance.student_id.in_(student_ids))
            .all()
        )
        matches = [
            {
                "student_id": r.student_id,
                "name": id_to_name.get(r.student_id, r.student_id),
                "value": r.attendance_percentage,
            }
            for r in rows
            if compare(r.attendance_percentage, threshold)
        ]
        considered = len(rows)
    else:
        column = SUBJECT_COLUMNS[subject] if subject else "average_marks"
        query = db.query(ExamMarks).filter(ExamMarks.student_id.in_(student_ids))
        if exam_type:
            query = query.filter(ExamMarks.exam_type == exam_type)

        rows = [r for r in query.all() if getattr(r, column) is not None]
        matches = [
            {
                "student_id": r.student_id,
                "name": id_to_name.get(r.student_id, r.student_id),
                "value": getattr(r, column),
                "exam_type": r.exam_type,
            }
            for r in rows
            if compare(getattr(r, column), threshold)
        ]
        considered = len(rows)

    matches.sort(key=lambda item: item["value"])

    _log(db, caller, "filter_students_by_criteria", target, True,
         detail=f"{len(matches)}/{considered} matched {metric} {operator} {threshold}")

    return {
        "class_name": class_name, "section": section,
        "metric": metric, "subject": subject,
        "exam_type": exam_type or ("all recorded exams" if metric == "marks" else None),
        "operator": operator, "threshold": threshold,
        "total_considered": considered,
        "matching_count": len(matches),
        "matching_students": matches,
    }


# ---------------------------------------------------------------------------
# Attendance analytics (principal)
# ---------------------------------------------------------------------------

def get_school_attendance_analytics(db: Session, caller: dict, days: int = 30, **_ignored) -> dict:
    """Tool: get_school_attendance_analytics -- Principal role only,
    school-wide read. Overall + per-class-section P/A counts, plus a
    below-75%-attendance alert list from OverallAttendance."""
    try:
        verify_principal_access(db, caller)
    except AuthorizationError as e:
        raise _to_tool_error(db, caller, "get_school_attendance_analytics", "school", e)

    cutoff = date.today()
    records = (
        db.query(DailyAttendance)
        .order_by(DailyAttendance.date.desc())
        .limit(days * 200)  # generous cap; real deployments should filter by date range server-side
        .all()
    )

    _log(db, caller, "get_school_attendance_analytics", "school", True, detail=f"{len(records)} record(s).")

    if not records:
        return {"message": "No attendance data found yet."}

    overall = {"present": 0, "absent": 0}
    by_class: dict[str, dict[str, int]] = {}
    for r in records:
        key = "present" if r.status == "P" else "absent"
        overall[key] += 1
        bucket = f"{r.class_name}{r.section}"
        by_class.setdefault(bucket, {"present": 0, "absent": 0})
        by_class[bucket][key] += 1

    low_attendance = [
        {"student_id": o.student_id, "percentage": o.attendance_percentage}
        for o in db.query(OverallAttendance).filter(OverallAttendance.attendance_percentage < 75).all()
    ]

    return {"overall": overall, "by_class_section": by_class, "below_75_percent": low_attendance}


# ---------------------------------------------------------------------------
# Principal lookups
# ---------------------------------------------------------------------------

def lookup_teachers_by_subject(db: Session, caller: dict, subject: str, **_ignored) -> dict:
    """Tool: lookup_teachers_by_subject -- Principal role only."""
    if subject not in SUBJECT_COLUMNS:
        raise ToolError(f"'{subject}' is not a recognized subject.")
    try:
        verify_principal_access(db, caller)
    except AuthorizationError as e:
        raise _to_tool_error(db, caller, "lookup_teachers_by_subject", subject, e)

    teachers = db.query(AuthTeacher).all()
    matches = [t for t in teachers if _normalize_subject(t, subject)]

    _log(db, caller, "lookup_teachers_by_subject", subject, True, detail=f"{len(matches)} match(es).")

    return {
        "subject": subject,
        "teachers": [
            {"teacher_id": t.teacher_id, "name": t.name, "classes": t.classes, "sections": t.sections}
            for t in matches
        ],
    }


def get_student_profile(db: Session, caller: dict, student_id: str, **_ignored) -> dict:
    """Tool: get_student_profile -- resolves through verify_student_bio_access,
    so a teacher only sees students in their own class/section, a parent
    only their linked child, a student only themself, and a principal any
    student."""
    try:
        student = verify_student_bio_access(db, caller, student_id)
    except AuthorizationError as e:
        raise _to_tool_error(db, caller, "get_student_profile", student_id, e)

    bio = db.query(StudentBio).filter(StudentBio.student_id == student.student_id).first()
    _log(db, caller, "get_student_profile", f"student_id={student.student_id}", True)

    return {
        "student_id": student.student_id, "name": student.name,
        "class_name": student.class_name, "section": student.section,
        "date_of_birth": bio.date_of_birth.isoformat() if bio and bio.date_of_birth else None,
        "gender": bio.gender if bio else None,
        "address": bio.address if bio else None,
        "contact_number": bio.contact_number if bio else None,
        "guardian_name": bio.guardian_name if bio else None,
        "blood_group": bio.blood_group if bio else None,
        "overall_average_score": bio.overall_average_score if bio else None,
    }


def get_teacher_profile(db: Session, caller: dict, teacher_id: str | None = None, **_ignored) -> dict:
    """Tool: get_teacher_profile -- teacher sees only their own profile;
    principal can look up any teacher."""
    try:
        teacher = verify_teacher_bio_access(db, caller, teacher_id)
    except AuthorizationError as e:
        raise _to_tool_error(db, caller, "get_teacher_profile", teacher_id, e)

    bio = db.query(TeacherBio).filter(TeacherBio.teacher_id == teacher.teacher_id).first()
    _log(db, caller, "get_teacher_profile", f"teacher_id={teacher.teacher_id}", True)

    return {
        "teacher_id": teacher.teacher_id, "name": teacher.name,
        "classes": teacher.classes, "sections": teacher.sections,
        "subject_handled": teacher.subject_handled,
        "qualification": bio.qualification if bio else None,
        "years_of_experience": bio.years_of_experience if bio else None,
        "joined_date": bio.joined_date.isoformat() if bio and bio.joined_date else None,
    }


# ---------------------------------------------------------------------------
# Messaging: warnings, doubts, parent queries
# ---------------------------------------------------------------------------

def send_warning(db: Session, caller: dict, target_student_id: str, message_content: str, **_ignored) -> dict:
    """Tool: send_warning -- Teacher role only, and only for a student in
    the teacher's own assigned class/section (verify_warning_access)."""
    if not message_content or not message_content.strip():
        raise ToolError("Warning message cannot be empty.")
    try:
        student = verify_warning_access(db, caller, target_student_id)
        teacher = get_authenticated_teacher(db, caller)
    except AuthorizationError as e:
        raise _to_tool_error(db, caller, "send_warning", target_student_id, e)

    db.add(TeacherCommunication(
        sender_role="teacher", sender_id=teacher.teacher_id,
        target_teacher_id=teacher.teacher_id, target_student_id=student.student_id,
        message_type="warning", message_content=message_content.strip(),
    ))
    db.commit()

    _log(db, caller, "send_warning", f"student_id={student.student_id}", True)
    return {"student_name": student.name, "status": "sent"}


def ask_teacher(db: Session, caller: dict, target_teacher_id: str, message_content: str,
                 subject: str | None = None, **_ignored) -> dict:
    """Tool: ask_teacher -- Student or Parent. Sends a 'doubt' (student) or
    'parent_query' (parent) to a teacher who actually teaches the caller's
    (or linked child's) class/section, verified via
    verify_teacher_communication_access before anything is written."""
    if not message_content or not message_content.strip():
        raise ToolError("Message cannot be empty.")

    role = caller["role"]
    if role not in ("student", "parent"):
        raise ToolError("Only students and parents can send this kind of message to a teacher.")

    try:
        verify_teacher_communication_access(
            db, caller, target_teacher_id=target_teacher_id, subject=subject,
        )
        sender_id = caller["id"]
    except AuthorizationError as e:
        raise _to_tool_error(db, caller, "ask_teacher", target_teacher_id, e)

    message_type = "doubt" if role == "student" else "parent_query"
    db.add(TeacherCommunication(
        sender_role=role, sender_id=str(sender_id),
        target_teacher_id=target_teacher_id, subject_handled=subject,
        message_type=message_type, message_content=message_content.strip(),
    ))
    db.commit()

    _log(db, caller, "ask_teacher", f"target_teacher_id={target_teacher_id}", True)
    return {"status": "sent", "message_type": message_type}


def get_my_communications(db: Session, caller: dict, unread_only: bool = False, **_ignored) -> dict:
    """Tool: get_my_communications -- Teacher role only, own inbox
    (messages targeted at this teacher's own teacher_id)."""
    try:
        teacher = get_authenticated_teacher(db, caller)
    except AuthorizationError as e:
        raise _to_tool_error(db, caller, "get_my_communications", "self", e)

    query = db.query(TeacherCommunication).filter(TeacherCommunication.target_teacher_id == teacher.teacher_id)
    if unread_only:
        query = query.filter(TeacherCommunication.is_read == False)  # noqa: E712
    rows = query.order_by(TeacherCommunication.created_at.desc()).all()

    _log(db, caller, "get_my_communications", "self", True, detail=f"{len(rows)} message(s).")

    return {
        "messages": [
            {
                "id": r.id, "from_role": r.sender_role, "from_id": r.sender_id,
                "student_id": r.target_student_id, "subject": r.subject_handled,
                "type": r.message_type, "content": r.message_content,
                "created_at": r.created_at.isoformat() if r.created_at else None,
                "is_read": r.is_read,
            }
            for r in rows
        ]
    }


def get_my_warnings(db: Session, caller: dict, **_ignored) -> dict:
    """Tool: get_my_warnings -- Student role only, own warnings. Parents
    can also read their linked child's warnings via get_child_warnings."""
    try:
        student = resolve_own_student(db, caller)
    except AuthorizationError as e:
        raise _to_tool_error(db, caller, "get_my_warnings", "self", e)

    rows = (
        db.query(TeacherCommunication)
        .filter(TeacherCommunication.target_student_id == student.student_id,
                TeacherCommunication.message_type == "warning")
        .order_by(TeacherCommunication.created_at.desc())
        .all()
    )
    _log(db, caller, "get_my_warnings", "self", True, detail=f"{len(rows)} warning(s).")
    return {"warnings": [{"content": r.message_content, "created_at": r.created_at.isoformat() if r.created_at else None} for r in rows]}


# ---------------------------------------------------------------------------
# Escalation
# ---------------------------------------------------------------------------

def request_escalation(db: Session, caller: dict, reason: str, confirmed: bool = False, **_ignored) -> dict:
    """Tool: request_escalation -- any verified role, own request only.
    Requires confirmed=True (defense-in-depth against the anti-hallucination
    rule -- see personas.py's escalation flow and escalation.py)."""
    if not reason or not reason.strip():
        raise ToolError("A reason is required before an escalation can be requested.")

    if not confirmed:
        _log(db, caller, "request_escalation", reason, False, detail="Not yet confirmed by user.")
        raise ToolError(
            "Escalation not yet submitted -- confirm with the user first, then "
            "call this tool again with confirmed=true."
        )

    outcome = _request_escalation(db, caller, reason)
    _log(db, caller, "request_escalation", f"escalation_id={outcome.request_id}", True,
         detail=f"status={outcome.status.value}")

    return {"escalation_id": outcome.request_id, "status": outcome.status.value, "message": outcome.message}


# ---------------------------------------------------------------------------
# Tool registry
# ---------------------------------------------------------------------------

TOOL_SCHEMAS = [
    {
        "name": "get_own_attendance",
        "description": "Get the calling student's own attendance for the last N days. Student role only; never accepts a student name/ID from the caller.",
        "input_schema": {"type": "object", "properties": {
            "days": {"type": "integer", "description": "Most-recent days to return. Defaults to 30."},
        }, "required": []},
    },
    {
        "name": "get_child_attendance",
        "description": "Get the calling parent's linked child's attendance for the last N days. Parent role only.",
        "input_schema": {"type": "object", "properties": {
            "days": {"type": "integer", "description": "Most-recent days to return. Defaults to 30."},
            "child_name": {"type": "string", "description": "Only needed if the parent has more than one linked child."},
        }, "required": []},
    },
    {
        "name": "mark_attendance",
        "description": "Mark one student present/absent for a date. Teacher role only, and only within the teacher's own assigned class/section.",
        "input_schema": {"type": "object", "properties": {
            "student_name": {"type": "string"},
            "status": {"type": "string", "enum": ["P", "A"]},
            "class_name": {"type": "string"},
            "section": {"type": "string"},
            "mark_date": {"type": "string", "description": "Optional ISO date (YYYY-MM-DD). Defaults to today."},
        }, "required": ["student_name", "status", "class_name", "section"]},
    },
    {
        "name": "submit_exam_marks",
        "description": "Enter/update one student's exam marks for one exam type, for subject(s) the teacher handles. Teacher role only.",
        "input_schema": {"type": "object", "properties": {
            "student_name": {"type": "string"},
            "exam_type": {"type": "string", "enum": ["term1", "term2", "term3", "final"]},
            "class_name": {"type": "string"},
            "section": {"type": "string"},
            "marks": {
                "type": "object",
                "description": "Subject -> mark (0-100), e.g. {\"Science\": 82}. Only include subjects the teacher handles.",
            },
        }, "required": ["student_name", "exam_type", "class_name", "section", "marks"]},
    },
    {
        "name": "get_own_marks",
        "description": "Get the calling student's own exam marks across all recorded exams. Student role only.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "get_child_marks",
        "description": "Get the calling parent's linked child's exam marks. Parent role only.",
        "input_schema": {"type": "object", "properties": {
            "child_name": {"type": "string", "description": "Only needed if the parent has more than one linked child."},
        }, "required": []},
    },
    {
        "name": "get_class_failure_report",
        "description": "Report how many students failed (<40) a subject in a class/section. Teacher (own class + own subject) or Principal (any).",
        "input_schema": {"type": "object", "properties": {
            "class_name": {"type": "string"},
            "section": {"type": "string"},
            "subject": {"type": "string", "enum": ["Maths", "Science", "Language", "Social", "Technology"]},
            "exam_type": {"type": "string", "enum": ["term1", "term2", "term3", "final"], "description": "Optional; all exams if omitted."},
        }, "required": ["class_name", "section", "subject"]},
    },
    {
        "name": "get_subject_performance_insights",
        "description": (
            "Get a class/section's real score distribution and struggling-student list for one subject, "
            "to base teaching-improvement suggestions and remedial recommendations on. Teacher (own class/section "
            "and own handled subject) or Principal (any). Returns data only -- synthesize the actual teaching "
            "advice yourself from the numbers returned; never state a statistic this tool didn't return."
        ),
        "input_schema": {"type": "object", "properties": {
            "class_name": {"type": "string"},
            "section": {"type": "string"},
            "subject": {"type": "string", "enum": ["Maths", "Science", "Language", "Social", "Technology"]},
            "exam_type": {"type": "string", "enum": ["term1", "term2", "term3", "final"], "description": "Optional; all exams if omitted."},
        }, "required": ["class_name", "section", "subject"]},
    },
    {
        "name": "get_attendance_patterns",
        "description": (
            "Get a class/section's real absenteeism pattern: overall attendance percentage, absences broken "
            "down by day of week (to find peak absence days), and the students who are regularly absent "
            "(below 75%). Teacher (own class/section) or Principal (any). Returns data only -- describe the "
            "pattern yourself from these numbers; never invent a percentage or trend not returned here."
        ),
        "input_schema": {"type": "object", "properties": {
            "class_name": {"type": "string"},
            "section": {"type": "string"},
            "days": {"type": "integer", "description": "How many most-recent attendance records per student to consider. Defaults to 30."},
        }, "required": ["class_name", "section"]},
    },
    {
        "name": "filter_students_by_criteria",
        "description": (
            "Filter students in a class/section by a natural-language numeric threshold, e.g. "
            "'Show students with attendance < 40%', 'Show students with marks > 90 in Term 1', "
            "'Show students who failed (< 40)'. Teacher (own class/section, and own handled subject "
            "if a subject is given) or Principal (any). Returns the real matching students (id, name, "
            "actual value) only -- never an invented or guessed list."
        ),
        "input_schema": {"type": "object", "properties": {
            "class_name": {"type": "string"},
            "section": {"type": "string"},
            "metric": {"type": "string", "enum": ["attendance_percentage", "marks"]},
            "operator": {"type": "string", "enum": ["<", ">", "<=", ">=", "=="]},
            "threshold": {"type": "number"},
            "subject": {
                "type": "string", "enum": ["Maths", "Science", "Language", "Social", "Technology"],
                "description": "Only used when metric='marks'. Omit for a generic (subject-agnostic) marks filter, which compares each exam's average_marks.",
            },
            "exam_type": {
                "type": "string", "enum": ["term1", "term2", "term3", "final"],
                "description": "Only used when metric='marks'. Optional; all exams if omitted.",
            },
        }, "required": ["class_name", "section", "metric", "operator", "threshold"]},
    },
    {
        "name": "get_school_attendance_analytics",
        "description": "School-wide attendance analytics with a below-75%-attendance alert list. Principal role only.",
        "input_schema": {"type": "object", "properties": {
            "days": {"type": "integer", "description": "Defaults to 30."},
        }, "required": []},
    },
    {
        "name": "lookup_teachers_by_subject",
        "description": "List all teachers who handle a given subject. Principal role only.",
        "input_schema": {"type": "object", "properties": {
            "subject": {"type": "string", "enum": ["Maths", "Science", "Language", "Social", "Technology"]},
        }, "required": ["subject"]},
    },
    {
        "name": "get_student_profile",
        "description": "Get a student's bio profile. Scope depends on caller role: student=self, parent=linked child, teacher=own class/section, principal=any.",
        "input_schema": {"type": "object", "properties": {
            "student_id": {"type": "string"},
        }, "required": ["student_id"]},
    },
    {
        "name": "get_teacher_profile",
        "description": "Get a teacher's bio profile. Teacher role sees only their own profile; Principal can look up any teacher by ID.",
        "input_schema": {"type": "object", "properties": {
            "teacher_id": {"type": "string", "description": "Required for principal callers; omit for a teacher looking up their own profile."},
        }, "required": []},
    },
    {
        "name": "send_warning",
        "description": "Send an attendance/behavior warning to a student. Teacher role only, and only for a student in the teacher's own class/section.",
        "input_schema": {"type": "object", "properties": {
            "target_student_id": {"type": "string"},
            "message_content": {"type": "string"},
        }, "required": ["target_student_id", "message_content"]},
    },
    {
        "name": "ask_teacher",
        "description": "Send a doubt (student) or query (parent) to a teacher who teaches the caller's/linked child's class and section.",
        "input_schema": {"type": "object", "properties": {
            "target_teacher_id": {"type": "string"},
            "message_content": {"type": "string"},
            "subject": {"type": "string", "enum": ["Maths", "Science", "Language", "Social", "Technology"]},
        }, "required": ["target_teacher_id", "message_content"]},
    },
    {
        "name": "get_my_warnings",
        "description": "Get the calling student's own warnings from teachers. Student role only.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "get_my_communications",
        "description": "Get messages (doubts/queries) sent to the calling teacher. Teacher role only.",
        "input_schema": {"type": "object", "properties": {
            "unread_only": {"type": "boolean"},
        }, "required": []},
    },
    {
        "name": "request_escalation",
        "description": (
            "Submit a request for a human teacher/management representative to follow up. "
            "Usable by ANY verified role. Only call with confirmed=true after the user has "
            "explicitly agreed; never claim success except by relaying the tool's returned status."
        ),
        "input_schema": {"type": "object", "properties": {
            "reason": {"type": "string"},
            "confirmed": {"type": "boolean"},
        }, "required": ["reason"]},
    },
]

TOOL_HANDLERS = {
    "get_own_attendance": get_own_attendance,
    "get_child_attendance": get_child_attendance,
    "mark_attendance": mark_attendance,
    "submit_exam_marks": submit_exam_marks,
    "get_own_marks": get_own_marks,
    "get_child_marks": get_child_marks,
    "get_class_failure_report": get_class_failure_report,
    "get_subject_performance_insights": get_subject_performance_insights,
    "get_attendance_patterns": get_attendance_patterns,
    "filter_students_by_criteria": filter_students_by_criteria,
    "get_school_attendance_analytics": get_school_attendance_analytics,
    "lookup_teachers_by_subject": lookup_teachers_by_subject,
    "get_student_profile": get_student_profile,
    "get_teacher_profile": get_teacher_profile,
    "send_warning": send_warning,
    "ask_teacher": ask_teacher,
    "get_my_warnings": get_my_warnings,
    "get_my_communications": get_my_communications,
    "request_escalation": request_escalation,
}


def run_tool(db: Session, caller: dict, tool_name: str, tool_input: dict) -> dict:
    """Single dispatch point the orchestrator calls. One choke point
    guarantees every tool call is checked and audited the same way."""
    handler = TOOL_HANDLERS.get(tool_name)
    if handler is None:
        raise ToolError(f"Unknown tool '{tool_name}'.")
    return handler(db, caller, **tool_input)