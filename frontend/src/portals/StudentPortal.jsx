import PortalShell from "../components/PortalShell";
import StudentProfilePanel from "../components/workspace/StudentProfilePanel";
import MessageTeacherPanel from "../components/workspace/MessageTeacherPanel";

/**
 * Student Portal. Shared PortalShell + ChatWidget handle attendance,
 * marks, and warnings entirely through natural-language chat (Phase 3
 * tools: get_own_attendance, get_own_marks, get_my_warnings). The
 * workspace panels here cover the two things that are more naturally a
 * form than a chat turn: viewing your own bio profile and composing a
 * message to a teacher.
 */
export default function StudentPortal() {
  return (
    <PortalShell
      role="student"
      workspace={
        <div className="grid gap-6 lg:grid-cols-2">
          <StudentProfilePanel />
          <MessageTeacherPanel role="student" />
        </div>
      }
    />
  );
}
