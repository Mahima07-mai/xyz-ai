"""
Shared pytest fixtures for the security/authorization test suite
(project plan section 2.2.E: "Unit tests for every tool handler's
authorization logic ... parent-cannot-see-other-child,
teacher-cannot-mark-other-class, etc.").

Uses an isolated in-memory SQLite database per test rather than the real
PostgreSQL instance, so the suite runs anywhere with no external
dependency and never touches real/demo data. The ORM models (model.py)
are plain SQLAlchemy and work unmodified against SQLite for this purpose.
"""
import os
import sys
from pathlib import Path

# app.config raises RuntimeError if OPENROUTER_API_KEY / JWT_SECRET are
# unset (see app/config.py's _require()) -- set harmless dummy values
# before any `app.*` module is imported, so the test suite doesn't
# require a real .env file to even collect.
os.environ.setdefault("OPENROUTER_API_KEY", "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")
os.environ.setdefault("JWT_SECRET", "c23f7902d184eb43b3512a84b2e88a0b06db2328114ef97ad76e82a392815f9d")
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Allow `import app.xxx` when pytest is run from backend/ or from tests/.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.ext.compiler import compiles

from app.database import Base
from app.model import (
    AuthParent,
    AuthPrincipal,
    AuthStudent,
    AuthTeacher,
    StudentBio,
    TeacherBio,
)

# model.py's columns (AuthTeacher.classes/sections/subject_handled, the
# UUID primary keys, etc.) intentionally use PostgreSQL-native JSONB/UUID
# types -- that's correct for the real deployment target, but SQLite has
# no built-in equivalent, so `Base.metadata.create_all()` against a plain
# SQLite engine fails with "can't render element of type JSONB" unless we
# tell the SQLite dialect how to substitute a compatible column type. This
# is a test-only compatibility shim; it doesn't change what gets deployed
# against real PostgreSQL.


@compiles(JSONB, "sqlite")
def _compile_jsonb_sqlite(element, compiler, **kw):
    return "JSON"


@compiles(UUID, "sqlite")
def _compile_uuid_sqlite(element, compiler, **kw):
    return "CHAR(36)"


@pytest.fixture()
def db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def seeded(db):
    """A minimal version of seed_data.py's fixtures, covering the same
    edge cases the plan calls out:
      - two same-first-name students in one class/section (Rahul Sharma,
        Rahul Verma in Class 8 - Section A)
      - two teachers each scoped to their own class/section (Class 8-A
        vs Class 9-B)
      - a parent linked to a child, and confirmation that a parent
        cannot reach a student they are NOT linked to

    Note on scope vs. the pre-refactor fixture: the pre-refactor schema
    let one parent (User + ParentChildLink) link to multiple children.
    The current role-scoped schema (model.py) deliberately gives each
    AuthParent record exactly one child_student_id -- see authz.py's
    verify_parent_access()/resolve_linked_child() docstrings ("The new
    schema permits one child per AuthParent record"). A parent with two
    children in school is therefore represented as two separate parent
    accounts in the current design, not one account with two linked
    children, so the old "parent linked to two children, ask for
    clarification" scenario no longer has anything to exercise -- there
    is no code path in the current authz.py that returns more than one
    child for a single parent record. This fixture reflects that: each
    AuthParent row here has exactly one child, and the corresponding
    test in test_security.py was updated to match (see the comment
    there) instead of asserting behavior the current schema cannot
    produce.
    """
    teacher = AuthTeacher(
        teacher_id="TCH101",
        name="Mr. Suresh Kumar",
        classes=["8"],
        sections=["A"],
        subject_handled=["Maths"],
        gmail="suresh.kumar@school.test",
        password_hash="x",
    )
    teacher2 = AuthTeacher(
        teacher_id="TCH102",
        name="Ms. Kavya Reddy",
        classes=["9"],
        sections=["B"],
        subject_handled=["Science"],
        gmail="kavya.reddy@school.test",
        password_hash="x",
    )
    principal = AuthPrincipal(
        principal_id="PRIN101",
        name="Dr. Meena Nair",
        gmail="meena.nair@school.test",
        password_hash="x",
    )
    db.add_all([teacher, teacher2, principal])
    db.flush()

    rahul = AuthStudent(
        student_id="STU101",
        name="Rahul Sharma",
        class_name="8",
        section="A",
        gmail="rahul.sharma@school.test",
        password_hash="x",
    )
    rahul2 = AuthStudent(
        student_id="STU102",
        name="Rahul Verma",
        class_name="8",
        section="A",
        gmail="rahul.verma@school.test",
        password_hash="x",
    )
    priya = AuthStudent(
        student_id="STU103",
        name="Priya Iyer",
        class_name="8",
        section="A",
        gmail="priya.iyer@school.test",
        password_hash="x",
    )
    arjun = AuthStudent(
        student_id="STU104",
        name="Arjun Das",
        class_name="9",
        section="B",
        gmail="arjun.das@school.test",
        password_hash="x",
    )
    db.add_all([rahul, rahul2, priya, arjun])
    db.flush()

    db.add_all([
        StudentBio(student_id=rahul.student_id, student_name=rahul.name),
        StudentBio(student_id=rahul2.student_id, student_name=rahul2.name),
        StudentBio(student_id=priya.student_id, student_name=priya.name),
        StudentBio(student_id=arjun.student_id, student_name=arjun.name),
        TeacherBio(teacher_id=teacher.teacher_id, teacher_name=teacher.name,
                   subject_handled=teacher.subject_handled),
        TeacherBio(teacher_id=teacher2.teacher_id, teacher_name=teacher2.name,
                   subject_handled=teacher2.subject_handled),
    ])

    parent = AuthParent(
        # AuthParent.parent_id is a PostgreSQL UUID column (see model.py);
        # even with as_uuid=False, SQLAlchemy's UUID type still round-trips
        # the value through Python's uuid.UUID(), so this must be a
        # syntactically valid UUID string, not an arbitrary slug.
        parent_id="a1111111-b222-c333-d444-e55555555555",
        name="Anita Sharma",
        child_student_id=rahul.student_id,  # linked to Rahul Sharma only
        gmail="anita.sharma@school.test",
        password_hash="x",
    )
    db.add(parent)
    db.commit()

    def caller_for(user) -> dict:
        """Build the {id, role, name} dict shape auth.get_current_user()
        returns, keyed off each role table's own primary key column."""
        role_pk = {
            AuthTeacher: "teacher_id",
            AuthStudent: "student_id",
            AuthParent: "parent_id",
            AuthPrincipal: "principal_id",
        }
        role_name = {
            AuthTeacher: "teacher",
            AuthStudent: "student",
            AuthParent: "parent",
            AuthPrincipal: "principal",
        }
        pk_col = role_pk[type(user)]
        return {
            "id": getattr(user, pk_col),
            "role": role_name[type(user)],
            "name": user.name,
        }

    return {
        "rahul": rahul, "rahul2": rahul2, "priya": priya, "arjun": arjun,
        "parent": parent, "teacher": teacher, "teacher2": teacher2,
        "principal": principal,
        "caller_for": caller_for,
    }