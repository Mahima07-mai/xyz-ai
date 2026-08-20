"""
ORM models for the school management system.

Schema follows the "Comprehensive System Refactoring Directive": role-scoped
auth tables, separate bio tables, daily + aggregated attendance, exam marks
with explicit per-subject columns, overall grading (populated only once all
four exams exist), and a single communications table used for warnings,
doubts, and parent queries.

Tables are created automatically on startup via
`Base.metadata.create_all(bind=engine)` in main.py -- there is no manual
migration step for local/dev use. For anything beyond local/dev, swap in
Alembic migrations instead of relying on create_all.

NOTE -- intentional deviation from the current directive's schema: the
named-subject columns/fields below (AuthTeacher.subject_handled,
TeacherBio.subject_handled, TeacherCommunication.subject_handled, and
ExamMarks's maths_mark/science_mark/language_mark/social_mark/
technology_mark) are a superset of the current directive's §2 schema,
which specifies only generic subject1_mark..subject5_mark columns and
no subject_handled field at all. This is a deliberate, kept deviation,
not an oversight -- see the "Known schema deviation" section of
xyz-ai/README.md for the full reasoning and the list of other files
(auth.py, authz.py, tools.py, the frontend marks grid) that share this
named-subject vocabulary and would need to change together if this
were ever reverted.
"""
import enum
import uuid
from datetime import date, datetime

from sqlalchemy import (
    Column, Integer, String, Float, Date, DateTime, ForeignKey, Boolean,
    Text, UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship

from .database import Base


def _uuid():
    return str(uuid.uuid4())


# ---------------------------------------------------------------------------
# A. Authentication & user tables
# ---------------------------------------------------------------------------

class AuthTeacher(Base):
    __tablename__ = "auth_teacher"

    teacher_id = Column(String, primary_key=True)  # username
    name = Column(String, nullable=False)
    classes = Column(JSONB, nullable=False, default=list)       # e.g. ["8", "9"]
    sections = Column(JSONB, nullable=False, default=list)      # e.g. ["A", "B"]
    subject_handled = Column(JSONB, nullable=False, default=list)  # e.g. ["Maths", "Science"]
    gmail = Column(String, unique=True, nullable=False)
    password_hash = Column(String, nullable=False)

    bio = relationship("TeacherBio", back_populates="teacher", uselist=False,
                        cascade="all, delete-orphan")


class AuthStudent(Base):
    __tablename__ = "auth_student"

    student_id = Column(String, primary_key=True)  # username
    name = Column(String, nullable=False)
    class_name = Column(String, nullable=False)
    section = Column(String, nullable=False)
    gmail = Column(String, unique=True, nullable=False)
    password_hash = Column(String, nullable=False)

    bio = relationship("StudentBio", back_populates="student", uselist=False,
                        cascade="all, delete-orphan")
    parents = relationship("AuthParent", back_populates="child")
    daily_attendance = relationship("DailyAttendance", back_populates="student",
                                     cascade="all, delete-orphan")
    overall_attendance = relationship("OverallAttendance", back_populates="student",
                                       uselist=False, cascade="all, delete-orphan")
    exam_marks = relationship("ExamMarks", back_populates="student",
                               cascade="all, delete-orphan")
    overall_grading = relationship("OverallGrading", back_populates="student",
                                    uselist=False, cascade="all, delete-orphan")


class AuthParent(Base):
    __tablename__ = "auth_parent"

    parent_id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    name = Column(String, nullable=False)
    child_student_id = Column(String, ForeignKey("auth_student.student_id"), nullable=False)
    gmail = Column(String, unique=True, nullable=False)
    password_hash = Column(String, nullable=False)

    child = relationship("AuthStudent", back_populates="parents")


class AuthPrincipal(Base):
    __tablename__ = "auth_principal"

    principal_id = Column(String, primary_key=True)  # username
    name = Column(String, nullable=False)
    gmail = Column(String, unique=True, nullable=False)
    password_hash = Column(String, nullable=False)


# ---------------------------------------------------------------------------
# B. Bio tables
# ---------------------------------------------------------------------------

class StudentBio(Base):
    __tablename__ = "student_bio"

    student_id = Column(String, ForeignKey("auth_student.student_id"), primary_key=True)
    student_name = Column(String, nullable=False)
    date_of_birth = Column(Date, nullable=True)
    gender = Column(String, nullable=True)
    address = Column(Text, nullable=True)
    contact_number = Column(String, nullable=True)
    guardian_name = Column(String, nullable=True)
    overall_average_score = Column(Float, nullable=True)  # synced from exam_marks
    blood_group = Column(String, nullable=True)

    student = relationship("AuthStudent", back_populates="bio")


class TeacherBio(Base):
    __tablename__ = "teacher_bio"

    teacher_id = Column(String, ForeignKey("auth_teacher.teacher_id"), primary_key=True)
    teacher_name = Column(String, nullable=False)
    subject_handled = Column(JSONB, nullable=False, default=list)
    date_of_birth = Column(Date, nullable=True)
    gender = Column(String, nullable=True)
    address = Column(Text, nullable=True)
    contact_number = Column(String, nullable=True)
    qualification = Column(String, nullable=True)
    years_of_experience = Column(Integer, nullable=True)
    joined_date = Column(Date, nullable=True)

    teacher = relationship("AuthTeacher", back_populates="bio")


# ---------------------------------------------------------------------------
# C. Attendance tables
# ---------------------------------------------------------------------------

class AttendanceStatus(str, enum.Enum):
    present = "P"
    absent = "A"


class DailyAttendance(Base):
    __tablename__ = "daily_attendance"
    __table_args__ = (
        UniqueConstraint("date", "student_id", name="uq_daily_attendance_date_student"),
    )

    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    date = Column(Date, nullable=False, default=date.today)
    class_name = Column(String, nullable=False)
    section = Column(String, nullable=False)
    student_id = Column(String, ForeignKey("auth_student.student_id"), nullable=False)
    status = Column(String, nullable=False)  # 'P' or 'A'

    student = relationship("AuthStudent", back_populates="daily_attendance")


class OverallAttendance(Base):
    __tablename__ = "overall_attendance"

    student_id = Column(String, ForeignKey("auth_student.student_id"), primary_key=True)
    total_present_days = Column(Integer, nullable=False, default=0)
    total_absent_days = Column(Integer, nullable=False, default=0)
    total_working_days = Column(Integer, nullable=False, default=0)
    attendance_percentage = Column(Float, nullable=False, default=0.0)

    student = relationship("AuthStudent", back_populates="overall_attendance")


# ---------------------------------------------------------------------------
# D. Marks & academic evaluation tables
# ---------------------------------------------------------------------------

class ExamType(str, enum.Enum):
    term1 = "term1"
    term2 = "term2"
    term3 = "term3"
    final = "final"


def compute_grade(average: float) -> str:
    if average >= 91:
        return "S"
    if average >= 80:
        return "A+"
    if average >= 70:
        return "A"
    if average >= 60:
        return "B"
    if average >= 50:
        return "C"
    if average >= 40:
        return "D"
    return "F"


class ExamMarks(Base):
    __tablename__ = "exam_marks"
    __table_args__ = (
        UniqueConstraint("student_id", "exam_type", name="uq_exam_marks_student_exam"),
    )

    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    student_id = Column(String, ForeignKey("auth_student.student_id"), nullable=False)
    class_name = Column(String, nullable=False)
    section = Column(String, nullable=False)
    exam_type = Column(String, nullable=False)  # 'term1' | 'term2' | 'term3' | 'final'

    maths_mark = Column(Float, nullable=True)
    science_mark = Column(Float, nullable=True)
    language_mark = Column(Float, nullable=True)
    social_mark = Column(Float, nullable=True)
    technology_mark = Column(Float, nullable=True)

    total_marks = Column(Float, nullable=True)
    average_marks = Column(Float, nullable=True)
    grade = Column(String, nullable=True)

    student = relationship("AuthStudent", back_populates="exam_marks")


class OverallGrading(Base):
    """Populated/updated only once term1, term2, term3, and final marks all
    exist for a given student (see tools.py: maybe_update_overall_grading)."""
    __tablename__ = "overall_grading"

    student_id = Column(String, ForeignKey("auth_student.student_id"), primary_key=True)
    term_average_weighted = Column(Float, nullable=True)  # avg(term1,2,3) scaled to /50
    final_exam_weighted = Column(Float, nullable=True)    # final exam /100 scaled to /50
    final_total_mark = Column(Float, nullable=True)       # out of 100
    final_overall_grade = Column(String, nullable=True)

    student = relationship("AuthStudent", back_populates="overall_grading")


# ---------------------------------------------------------------------------
# E. System messaging & communication
# ---------------------------------------------------------------------------

class SenderRole(str, enum.Enum):
    teacher = "teacher"
    student = "student"
    parent = "parent"


class MessageType(str, enum.Enum):
    warning = "warning"
    doubt = "doubt"
    parent_query = "parent_query"


class TeacherCommunication(Base):
    __tablename__ = "teacher_communications"

    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    sender_role = Column(String, nullable=False)  # 'teacher' | 'student' | 'parent'
    sender_id = Column(String, nullable=False)
    target_teacher_id = Column(String, ForeignKey("auth_teacher.teacher_id"), nullable=False)
    target_student_id = Column(String, ForeignKey("auth_student.student_id"), nullable=True)
    subject_handled = Column(String, nullable=True)
    message_type = Column(String, nullable=False)  # 'warning' | 'doubt' | 'parent_query'
    message_content = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    is_read = Column(Boolean, default=False, nullable=False)


# ---------------------------------------------------------------------------
# Retained from the previous schema: audit log (not part of the directive,
# but still relied on by the security test suite / authz layer).
# ---------------------------------------------------------------------------

class AuditLog(Base):
    __tablename__ = "audit_log"

    id = Column(Integer, primary_key=True)
    timestamp = Column(DateTime, default=datetime.utcnow)
    actor_id = Column(String, nullable=False)
    actor_role = Column(String, nullable=False)
    tool_name = Column(String, nullable=False)
    target_description = Column(String, nullable=True)
    allowed = Column(Boolean, nullable=False)
    detail = Column(Text, nullable=True)

# ---------------------------------------------------------------------------
# F. Escalation requests (Phase 3)
#
# Backs escalation.py's "never claim a human was contacted unless a mock
# service genuinely confirms it" requirement. Any authenticated role may
# create one; a caller can only ever read back THEIR OWN rows (enforced in
# escalation.py, keyed off requested_by_id which comes from the verified
# JWT, never from chat text).
# ---------------------------------------------------------------------------

class EscalationStatus(str, enum.Enum):
    pending = "pending"
    confirmed = "confirmed"
    failed = "failed"


class EscalationRequest(Base):
    __tablename__ = "escalation_requests"

    id = Column(Integer, primary_key=True)
    requested_by_id = Column(String, nullable=False)     # caller["id"] -- teacher_id / student_id / parent_id (uuid) / principal_id
    requested_by_role = Column(String, nullable=False)    # caller["role"]
    reason = Column(Text, nullable=False)
    status = Column(String, nullable=False, default=EscalationStatus.pending.value)
    created_at = Column(DateTime, default=datetime.utcnow)