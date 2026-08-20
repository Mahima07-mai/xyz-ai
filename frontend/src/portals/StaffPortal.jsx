import PortalShell from "../components/PortalShell";
import TeacherWorkspace from "../components/workspace/TeacherWorkspace";

/**
 * Staff Portal -- the teacher-facing portal. Backend role key is
 * "teacher" (see backend/app/model.py AuthTeacher); the portal/repo
 * name and the role key are intentionally allowed to differ.
 *
 * TeacherWorkspace covers Flow C (attendance grid), Flow D (marks
 * grid), and Flow E (send warning / inbox) as real interactive tables
 * -- the directive is explicit these need an "Interactive UI Table",
 * which a chat turn can't naturally render. Chat (below, via
 * PortalShell) remains fully capable of the same actions in natural
 * language, plus the Phase 4 AI analytics (teaching insights,
 * absentee patterns) and class-failure reports, which are
 * conversational by nature and stay chat-only.
 */
export default function StaffPortal() {
  return <PortalShell role="teacher" workspace={<TeacherWorkspace />} />;
}
