"""
Authentication (Phase 2).

Four independent role tables (auth_teacher, auth_student, auth_parent,
auth_principal) replace the old single `User` table, so there is no
longer one universal "user_id" -- identity is always (role, id-within-
that-role-table). Every login issues a JWT carrying that VERIFIED
(role, id, name), signed with JWT_SECRET. Every downstream layer
(authz.py, tools.py) trusts ONLY that token, never anything the caller
types in chat: a message that says "actually I'm the principal" cannot
change what a request is allowed to touch, because the role is read
from the signed token, not from message text.

Passwords are hashed with bcrypt before they ever touch the database --
`AuthTeacher.password_hash` etc. never holds a plaintext password, and
login compares hashes, never raw strings.
"""
import re
import uuid
from datetime import date, datetime, timedelta, timezone

import bcrypt
import jwt
from fastapi import Header, HTTPException
from pydantic import BaseModel, field_validator
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .config import settings
from .model import AuthParent, AuthPrincipal, AuthStudent, AuthTeacher, StudentBio, TeacherBio

JWT_ALGORITHM = "HS256"
JWT_EXPIRY_MINUTES = 120

ALLOWED_SUBJECTS = {"Maths", "Science", "Language", "Social", "Technology"}
ALLOWED_ROLES = {"teacher", "student", "parent", "principal"}

# role -> ORM model, and role -> that model's user-facing primary-key column.
# (parent_id is a server-generated UUID, never typed by the user, so
# parents identify themselves by gmail -- see _find_user_by_identifier.)
ROLE_TABLES = {
    "teacher": AuthTeacher,
    "student": AuthStudent,
    "parent": AuthParent,
    "principal": AuthPrincipal,
}
ROLE_PK = {
    "teacher": "teacher_id",
    "student": "student_id",
    "parent": "parent_id",
    "principal": "principal_id",
}

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _validate_email(value: str) -> str:
    if not value or not _EMAIL_RE.match(value):
        raise ValueError("Not a valid email address.")
    return value


def _validate_role(value: str) -> str:
    role = (value or "").strip().lower()
    if role not in ALLOWED_ROLES:
        raise ValueError(f"role must be one of {sorted(ALLOWED_ROLES)}.")
    return role


def _validate_subjects(subjects: list[str]) -> list[str]:
    if not subjects:
        raise ValueError("At least one subject must be specified.")
    bad = sorted(set(subjects) - ALLOWED_SUBJECTS)
    if bad:
        raise ValueError(
            f"Unknown subject(s): {', '.join(bad)}. Allowed: {', '.join(sorted(ALLOWED_SUBJECTS))}."
        )
    return subjects


def _non_empty(values: list[str]) -> list[str]:
    if not values:
        raise ValueError("At least one value is required.")
    return values


# ---------------------------------------------------------------------------
# Password hashing
# ---------------------------------------------------------------------------

def hash_password(raw_password: str) -> str:
    if not raw_password or len(raw_password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters long.")
    return bcrypt.hashpw(raw_password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(raw_password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(raw_password.encode("utf-8"), password_hash.encode("utf-8"))
    except (ValueError, AttributeError):
        # Malformed/empty hash in the DB -- fail closed, never raise a
        # stack trace back to the caller.
        return False


def _check_passwords_match(password: str, verify_password_field: str) -> None:
    if password != verify_password_field:
        raise HTTPException(status_code=400, detail="password and verify_password do not match.")


# ---------------------------------------------------------------------------
# Registration request schemas
# ---------------------------------------------------------------------------

class TeacherRegisterRequest(BaseModel):
    name: str
    teacher_id: str
    subject_handled: list[str]
    classes: list[str]
    sections: list[str]
    gmail: str
    password: str
    verify_password: str

    @field_validator("subject_handled")
    @classmethod
    def _check_subjects(cls, v: list[str]) -> list[str]:
        return _validate_subjects(v)

    @field_validator("classes", "sections")
    @classmethod
    def _check_non_empty(cls, v: list[str]) -> list[str]:
        return _non_empty(v)

    @field_validator("gmail")
    @classmethod
    def _check_gmail(cls, v: str) -> str:
        return _validate_email(v)


class StudentRegisterRequest(BaseModel):
    name: str
    student_id: str
    class_name: str
    section: str
    gmail: str
    password: str
    verify_password: str
    # Bio fields collected at registration (frontend/src/portals/LoginPortal.jsx)
    # and written straight into student_bio -- all optional here since
    # student_bio itself has them as nullable columns.
    gender: str | None = None
    date_of_birth: date | None = None
    guardian_name: str | None = None
    contact_number: str | None = None
    blood_group: str | None = None

    @field_validator("gmail")
    @classmethod
    def _check_gmail(cls, v: str) -> str:
        return _validate_email(v)

    @field_validator("gender", "guardian_name", "contact_number", "blood_group", mode="before")
    @classmethod
    def _blank_to_none(cls, v):
        # Frontend sends "" for untouched optional fields -- treat that
        # the same as omitted rather than storing an empty string.
        if isinstance(v, str) and v.strip() == "":
            return None
        return v


class ParentRegisterRequest(BaseModel):
    name: str
    child_student_id: str
    gmail: str
    password: str
    verify_password: str

    @field_validator("gmail")
    @classmethod
    def _check_gmail(cls, v: str) -> str:
        return _validate_email(v)


class PrincipalRegisterRequest(BaseModel):
    name: str
    principal_id: str
    gmail: str
    password: str
    verify_password: str

    @field_validator("gmail")
    @classmethod
    def _check_gmail(cls, v: str) -> str:
        return _validate_email(v)


class LoginRequest(BaseModel):
    role: str
    identifier: str  # teacher_id / student_id / principal_id, or gmail for any role
    password: str

    @field_validator("role")
    @classmethod
    def _check_role(cls, v: str) -> str:
        return _validate_role(v)


class ForgotPasswordRequest(BaseModel):
    role: str
    gmail: str
    new_password: str
    verify_new_password: str

    @field_validator("role")
    @classmethod
    def _check_role(cls, v: str) -> str:
        return _validate_role(v)

    @field_validator("gmail")
    @classmethod
    def _check_gmail(cls, v: str) -> str:
        return _validate_email(v)


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

def register_teacher(db: Session, payload: TeacherRegisterRequest) -> AuthTeacher:
    _check_passwords_match(payload.password, payload.verify_password)
    if db.query(AuthTeacher).filter(AuthTeacher.teacher_id == payload.teacher_id).first():
        raise HTTPException(status_code=400, detail=f"Teacher ID '{payload.teacher_id}' is already registered.")
    if db.query(AuthTeacher).filter(AuthTeacher.gmail == payload.gmail).first():
        raise HTTPException(status_code=400, detail="This Gmail address is already registered as a teacher.")

    teacher = AuthTeacher(
        teacher_id=payload.teacher_id,
        name=payload.name,
        classes=payload.classes,
        sections=payload.sections,
        subject_handled=payload.subject_handled,
        gmail=payload.gmail,
        password_hash=hash_password(payload.password),
    )
    db.add(teacher)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=400, detail="Teacher ID or Gmail is already registered.")

    db.add(TeacherBio(
        teacher_id=teacher.teacher_id,
        teacher_name=payload.name,
        subject_handled=payload.subject_handled,
    ))
    db.commit()
    db.refresh(teacher)
    return teacher


def register_student(db: Session, payload: StudentRegisterRequest) -> AuthStudent:
    _check_passwords_match(payload.password, payload.verify_password)
    if db.query(AuthStudent).filter(AuthStudent.student_id == payload.student_id).first():
        raise HTTPException(status_code=400, detail=f"Student ID '{payload.student_id}' is already registered.")
    if db.query(AuthStudent).filter(AuthStudent.gmail == payload.gmail).first():
        raise HTTPException(status_code=400, detail="This Gmail address is already registered as a student.")

    student = AuthStudent(
        student_id=payload.student_id,
        name=payload.name,
        class_name=payload.class_name,
        section=payload.section,
        gmail=payload.gmail,
        password_hash=hash_password(payload.password),
    )
    db.add(student)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=400, detail="Student ID or Gmail is already registered.")

    db.add(StudentBio(
        student_id=student.student_id,
        student_name=payload.name,
        gender=payload.gender,
        date_of_birth=payload.date_of_birth,
        guardian_name=payload.guardian_name,
        contact_number=payload.contact_number,
        blood_group=payload.blood_group,
    ))
    db.commit()
    db.refresh(student)
    return student


def register_parent(db: Session, payload: ParentRegisterRequest) -> AuthParent:
    _check_passwords_match(payload.password, payload.verify_password)

    child = db.query(AuthStudent).filter(AuthStudent.student_id == payload.child_student_id).first()
    if not child:
        raise HTTPException(
            status_code=404,
            detail=(
                f"No student found with ID '{payload.child_student_id}'. "
                "The child must already have a student account before a parent can link to it."
            ),
        )
    if db.query(AuthParent).filter(AuthParent.gmail == payload.gmail).first():
        raise HTTPException(status_code=400, detail="This Gmail address is already registered as a parent.")

    parent = AuthParent(
        parent_id=str(uuid.uuid4()),
        name=payload.name,
        child_student_id=payload.child_student_id,
        gmail=payload.gmail,
        password_hash=hash_password(payload.password),
    )
    db.add(parent)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=400, detail="This Gmail address is already registered as a parent.")
    db.refresh(parent)
    return parent


def register_principal(db: Session, payload: PrincipalRegisterRequest) -> AuthPrincipal:
    _check_passwords_match(payload.password, payload.verify_password)
    if db.query(AuthPrincipal).filter(AuthPrincipal.principal_id == payload.principal_id).first():
        raise HTTPException(status_code=400, detail=f"Principal ID '{payload.principal_id}' is already registered.")
    if db.query(AuthPrincipal).filter(AuthPrincipal.gmail == payload.gmail).first():
        raise HTTPException(status_code=400, detail="This Gmail address is already registered as a principal.")

    principal = AuthPrincipal(
        principal_id=payload.principal_id,
        name=payload.name,
        gmail=payload.gmail,
        password_hash=hash_password(payload.password),
    )
    db.add(principal)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=400, detail="Principal ID or Gmail is already registered.")
    db.refresh(principal)
    return principal


# ---------------------------------------------------------------------------
# Login
# ---------------------------------------------------------------------------

def _find_user_by_identifier(db: Session, role: str, identifier: str):
    """Teacher/Student/Principal can log in with their chosen ID (their
    'username') OR their gmail. Parent has no user-chosen ID -- parent_id
    is a server-generated UUID -- so parents always identify by gmail."""
    model = ROLE_TABLES[role]
    if role == "parent":
        return db.query(model).filter(model.gmail == identifier).first()
    pk_col = getattr(model, ROLE_PK[role])
    return db.query(model).filter((pk_col == identifier) | (model.gmail == identifier)).first()


def issue_session_token(role: str, subject_id: str, name: str) -> str:
    """Encodes the DB-VERIFIED (role, id, name) into a signed token. This
    token is the single source of truth for identity from here on --
    authz.py never trusts a role/id typed in chat."""
    payload = {
        "sub": subject_id,
        "role": role,
        "name": name,
        "exp": datetime.now(timezone.utc) + timedelta(minutes=JWT_EXPIRY_MINUTES),
    }
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=JWT_ALGORITHM)


def decode_session_token(token: str) -> dict:
    try:
        return jwt.decode(token, settings.JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Session expired, please log in again.")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid session token.")


def login(db: Session, payload: LoginRequest) -> str:
    user = _find_user_by_identifier(db, payload.role, payload.identifier)
    # Deliberately the SAME error for "no such account" and "wrong
    # password" -- never let a login attempt reveal whether an
    # identifier/gmail exists in a given role table.
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid credentials.")
    subject_id = getattr(user, ROLE_PK[payload.role])
    return issue_session_token(payload.role, subject_id, user.name)


def get_current_user(authorization: str = Header(...)) -> dict:
    """FastAPI dependency used by every protected route. Expects
    `Authorization: Bearer <token>`. Returns the VERIFIED identity dict
    {id, role, name} -- authz.py and tools.py check against this, never
    against the chat message text."""
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or malformed Authorization header.")
    token = authorization.removeprefix("Bearer ").strip()
    payload = decode_session_token(token)
    return {"id": payload["sub"], "role": payload["role"], "name": payload["name"]}


# ---------------------------------------------------------------------------
# Forgot password
# ---------------------------------------------------------------------------

def forgot_password(db: Session, payload: ForgotPasswordRequest) -> None:
    _check_passwords_match(payload.new_password, payload.verify_new_password)
    model = ROLE_TABLES[payload.role]
    user = db.query(model).filter(model.gmail == payload.gmail).first()
    if not user:
        raise HTTPException(status_code=404, detail="No account found for that Gmail address and role.")
    user.password_hash = hash_password(payload.new_password)
    db.commit()