/**
 * Role metadata shared across the login screen, portal shells, and the
 * chat widget. Deliberately mirrors backend/app/model.py's role-scoped
 * tables ("student" | "parent" | "teacher" | "principal") and
 * backend/app/personas.py's per-role framing -- the frontend never
 * invents its own role vocabulary.
 *
 * Nothing here is a source of authorization truth: it's presentation
 * only. The verified role always comes back from the backend on the
 * login response's JWT (decoded server-side on every request), never
 * from anything picked here.
 */

export const ROLES = {
  student: {
    key: "student",
    label: "Student",
    portalName: "Student Portal",
    tagline: "Your attendance, marks, and messages, one question away.",
    tone: "Friendly and encouraging.",
    accent: "chalk",
    pkField: "student_id",
    pkLabel: "Student ID",
    examplePrompt: "What is my attendance?",
    quickActions: [
      "What is my attendance?",
      "What are my marks so far?",
      "Do I have any warnings from a teacher?",
      "I'd like to talk to a teacher.",
    ],
  },
  parent: {
    key: "parent",
    label: "Parent",
    portalName: "Parent Portal",
    tagline: "Check in on your child's attendance, marks, and messages.",
    tone: "Warm and reassuring.",
    accent: "marigold",
    pkField: "parent_id",
    pkLabel: "Parent account",
    examplePrompt: "How much attendance does my child have?",
    quickActions: [
      "How much attendance does my child have?",
      "What are my child's marks so far?",
      "I'd like to speak with my child's teacher.",
    ],
  },
  teacher: {
    key: "teacher",
    label: "Teacher",
    portalName: "Staff Portal",
    tagline: "Attendance, marks, teaching insights, and messages for your class.",
    tone: "Efficient and professional.",
    accent: "rust",
    pkField: "teacher_id",
    pkLabel: "Teacher ID",
    examplePrompt: "Mark Rahul absent today.",
    quickActions: [
      "Mark Rahul absent today.",
      "How many students failed Science in my class?",
      "How can I improve my students who scored low?",
      "What's the pattern of absentees in my class?",
      "I need to escalate an issue to management.",
    ],
  },
  principal: {
    key: "principal",
    label: "Principal",
    portalName: "Management Portal",
    tagline: "School-wide attendance, marks, and staffing, at a glance.",
    tone: "Professional and concise.",
    accent: "ink",
    pkField: "principal_id",
    pkLabel: "Principal ID",
    examplePrompt: "What is the overall attendance?",
    quickActions: [
      "What is the overall attendance?",
      "Give me the list of teachers handling Science.",
      "What's the pattern of absentees in Class 9 Section B?",
      "Escalate an issue to the support desk.",
    ],
  },
};

export const ROLE_ORDER = ["student", "parent", "teacher", "principal"];

// Mirrors backend/app/authz.py's ALLOWED_SUBJECTS exactly -- the five
// subjects the whole system (registration, marks, class-failure reports,
// teaching-insight reports) is scoped to.
export const SUBJECTS = ["Maths", "Science", "Language", "Social", "Technology"];

export function roleMeta(roleKey) {
  return (
    ROLES[roleKey] ?? {
      key: roleKey,
      label: roleKey,
      portalName: "Portal",
      tagline: "",
      tone: "",
      accent: "chalk",
      pkField: "id",
      pkLabel: "ID",
      examplePrompt: "",
      quickActions: [],
    }
  );
}

// As of Day 4, the live list of fluent-response languages (and the
// full 11-language target list + STT locales) is fetched from the
// backend at runtime -- see hooks/useLanguages.js and
// backend/app/language.py. This file no longer hardcodes a language
// list, so the frontend can't drift out of sync with what the backend
// actually supports.
