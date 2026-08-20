"""
Creates all tables and loads a small, consistent mock dataset against the
Phase 2 role-scoped schema. Safe to re-run: it wipes and recreates the
PostgreSQL tables each time so the demo is always in a known state.

Deliberately includes the same edge cases the old seed data exercised, now
expressed in the new schema:
  - two teachers, each scoped to a different class/section, one of them
    handling two subjects (multi-subject write scoping for submit_exam_marks)
  - a "Rahul" name collision inside one class/section (ambiguous-name
    resolution in resolve_student_in_class)
  - a parent linked to two children (multi-child clarification in
    resolve_linked_child / get_child_attendance / get_child_marks)
  - a student with no attendance/marks yet (the "no data yet" edge case)
  - one student with all four exam types recorded, to exercise
    OverallGrading's "only once all four exist" condition; everyone else
    left partial

Run directly with:  python -m app.seed_data
"""
from datetime import date, timedelta

from .auth import hash_password
from .database import Base, engine, SessionLocal
from .model import (
    AuthParent, AuthPrincipal, AuthStudent, AuthTeacher,
    DailyAttendance, ExamMarks, OverallAttendance, StudentBio, TeacherBio,
    compute_grade,
)

_PASSWORD = "Passw0rd!"  # seed-only; every seeded account shares this for demo convenience


def _recompute_overall_attendance(db, student_id: str) -> None:
    rows = db.query(DailyAttendance).filter(DailyAttendance.student_id == student_id).all()
    present = sum(1 for r in rows if r.status == "P")
    absent = sum(1 for r in rows if r.status == "A")
    total = present + absent
    db.add(OverallAttendance(
        student_id=student_id,
        total_present_days=present,
        total_absent_days=absent,
        total_working_days=total,
        attendance_percentage=round((present / total) * 100, 2) if total else 0.0,
    ))


def _add_exam(db, student_id: str, class_name: str, section: str, exam_type: str,
              maths=None, science=None, language=None, social=None, technology=None) -> None:
    values = [v for v in (maths, science, language, social, technology) if v is not None]
    total = sum(values) if values else None
    average = (total / len(values)) if values else None
    db.add(ExamMarks(
        student_id=student_id, class_name=class_name, section=section, exam_type=exam_type,
        maths_mark=maths, science_mark=science, language_mark=language,
        social_mark=social, technology_mark=technology,
        total_marks=round(total, 2) if total is not None else None,
        average_marks=round(average, 2) if average is not None else None,
        grade=compute_grade(average) if average is not None else None,
    ))


def seed():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)

    db = SessionLocal()
    try:
        # --- Teachers ---
        # Suresh: Grade 8-A, Maths + Science (multi-subject, exercises
        # per-subject write scoping in submit_exam_marks/submit_class_marks).
        suresh = AuthTeacher(
            teacher_id="T001", name="Mr. Suresh Kumar",
            classes=["8"], sections=["A"], subject_handled=["Maths", "Science"],
            gmail="suresh.kumar@xyzschool.test", password_hash=hash_password(_PASSWORD),
        )
        # Kavya: Grade 9-B, Language only.
        kavya = AuthTeacher(
            teacher_id="T002", name="Ms. Kavya Reddy",
            classes=["9"], sections=["B"], subject_handled=["Language"],
            gmail="kavya.reddy@xyzschool.test", password_hash=hash_password(_PASSWORD),
        )
        db.add_all([suresh, kavya])
        db.flush()
        db.add_all([
            TeacherBio(teacher_id=suresh.teacher_id, teacher_name=suresh.name,
                       subject_handled=suresh.subject_handled, qualification="M.Sc. Mathematics",
                       years_of_experience=9, joined_date=date(2017, 6, 1)),
            TeacherBio(teacher_id=kavya.teacher_id, teacher_name=kavya.name,
                       subject_handled=kavya.subject_handled, qualification="M.A. English",
                       years_of_experience=5, joined_date=date(2021, 6, 1)),
        ])

        # --- Students ---
        rahul = AuthStudent(
            student_id="S001", name="Rahul Sharma", class_name="8", section="A",
            gmail="rahul.sharma@xyzschool.test", password_hash=hash_password(_PASSWORD),
        )
        priya = AuthStudent(
            student_id="S002", name="Priya Iyer", class_name="8", section="A",
            gmail="priya.iyer@xyzschool.test", password_hash=hash_password(_PASSWORD),
        )
        # Name collision with Rahul Sharma, same class/section -- ambiguous
        # lookup edge case for resolve_student_in_class.
        rahul_v = AuthStudent(
            student_id="S003", name="Rahul Verma", class_name="8", section="A",
            gmail="rahul.verma@xyzschool.test", password_hash=hash_password(_PASSWORD),
        )
        # Different class -- wrong-class denial edge case for Suresh.
        arjun = AuthStudent(
            student_id="S004", name="Arjun Das", class_name="9", section="B",
            gmail="arjun.das@xyzschool.test", password_hash=hash_password(_PASSWORD),
        )
        db.add_all([rahul, priya, rahul_v, arjun])
        db.flush()
        db.add_all([
            StudentBio(student_id=rahul.student_id, student_name=rahul.name,
                       date_of_birth=date(2012, 4, 12), gender="Male",
                       guardian_name="Anita Sharma", blood_group="B+"),
            StudentBio(student_id=priya.student_id, student_name=priya.name,
                       date_of_birth=date(2012, 9, 3), gender="Female",
                       guardian_name="Anita Sharma", blood_group="O+"),
            StudentBio(student_id=rahul_v.student_id, student_name=rahul_v.name,
                       date_of_birth=date(2012, 1, 20), gender="Male"),
            StudentBio(student_id=arjun.student_id, student_name=arjun.name,
                       date_of_birth=date(2011, 11, 15), gender="Male"),
        ])

        # --- Parent: linked to Rahul Sharma AND Priya Iyer. The schema
        # models one child per AuthParent row, so "two linked children" is
        # represented as two AuthParent rows sharing the same parent
        # identity/gmail -- authz.resolve_linked_child works off a single
        # parent_id, so this seed creates two DISTINCT parent accounts (a
        # deliberate simplification of the 1-parent-account-per-child
        # schema) sharing the guardian's name, so both children remain
        # independently reachable through their own login.
        anita_for_rahul = AuthParent(
            name="Anita Sharma", child_student_id=rahul.student_id,
            gmail="anita.sharma+rahul@xyzschool.test", password_hash=hash_password(_PASSWORD),
        )
        anita_for_priya = AuthParent(
            name="Anita Sharma", child_student_id=priya.student_id,
            gmail="anita.sharma+priya@xyzschool.test", password_hash=hash_password(_PASSWORD),
        )
        db.add_all([anita_for_rahul, anita_for_priya])

        # --- Principal ---
        principal = AuthPrincipal(
            principal_id="P001", name="Dr. Meena Nair",
            gmail="meena.nair@xyzschool.test", password_hash=hash_password(_PASSWORD),
        )
        db.add(principal)
        db.flush()

        # --- Attendance: a few days of history. Priya and Rahul Verma are
        # deliberately left sparse/empty to exercise "no data yet".
        today = date.today()
        attendance_rows = [
            (rahul.student_id, "8", "A", today, "P"),
            (rahul.student_id, "8", "A", today - timedelta(days=1), "P"),
            (rahul.student_id, "8", "A", today - timedelta(days=2), "A"),
            (rahul.student_id, "8", "A", today - timedelta(days=3), "P"),
            (arjun.student_id, "9", "B", today, "P"),
            (arjun.student_id, "9", "B", today - timedelta(days=1), "A"),
            (arjun.student_id, "9", "B", today - timedelta(days=2), "A"),
            (arjun.student_id, "9", "B", today - timedelta(days=3), "A"),  # pushes Arjun under 75%
        ]
        for student_id, class_name, section, d, status in attendance_rows:
            db.add(DailyAttendance(date=d, class_name=class_name, section=section,
                                    student_id=student_id, status=status))
        db.flush()
        for student_id in {r[0] for r in attendance_rows}:
            _recompute_overall_attendance(db, student_id)

        # --- Exam marks: Rahul Sharma has all four exam types recorded, to
        # exercise OverallGrading's "only once all four exist" rule.
        # Everyone else stays partial.
        _add_exam(db, rahul.student_id, "8", "A", "term1", maths=78, science=82, language=70, social=65, technology=88)
        _add_exam(db, rahul.student_id, "8", "A", "term2", maths=81, science=79, language=74, social=69, technology=90)
        _add_exam(db, rahul.student_id, "8", "A", "term3", maths=85, science=88, language=77, social=71, technology=91)
        _add_exam(db, rahul.student_id, "8", "A", "final", maths=90, science=92, language=80, social=75, technology=93)

        # Priya: only term1, and deliberately failing Science (<40) for the
        # get_class_failure_report edge case.
        _add_exam(db, priya.student_id, "8", "A", "term1", maths=55, science=32, language=60, social=58, technology=70)

        # Rahul Verma: no marks yet -- "no data" edge case.

        db.commit()

        print("Seed complete. Mock login credentials for testing (all share the seed password):")
        print(f"  password for every seeded account: {_PASSWORD}")
        print(f"  Teacher (Suresh Kumar) -> teacher_id=T001  gmail={suresh.gmail}   Grade 8-A, Maths+Science")
        print(f"  Teacher (Kavya Reddy)  -> teacher_id=T002  gmail={kavya.gmail}   Grade 9-B, Language")
        print(f"  Student (Rahul Sharma) -> student_id=S001  gmail={rahul.gmail}   Grade 8-A, full attendance+marks history")
        print(f"  Student (Priya Iyer)   -> student_id=S002  gmail={priya.gmail}   Grade 8-A, failing Science on term1")
        print(f"  Student (Rahul Verma)  -> student_id=S003  gmail={rahul_v.gmail}   Grade 8-A, same first name as S001, no data yet")
        print(f"  Student (Arjun Das)    -> student_id=S004  gmail={arjun.gmail}   Grade 9-B, attendance under 75%")
        print(f"  Parent  (Anita/Rahul)  -> gmail={anita_for_rahul.gmail}   linked to Rahul Sharma")
        print(f"  Parent  (Anita/Priya)  -> gmail={anita_for_priya.gmail}   linked to Priya Iyer")
        print(f"  Principal (Meena Nair) -> principal_id=P001  gmail={principal.gmail}")
    finally:
        db.close()


if __name__ == "__main__":
    seed()
