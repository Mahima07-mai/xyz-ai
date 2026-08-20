import PortalShell from "../components/PortalShell";
import ChildProfilePanel from "../components/workspace/ChildProfilePanel";
import MessageTeacherPanel from "../components/workspace/MessageTeacherPanel";

/**
 * Parent Portal. Chat (via PortalShell/ChatWidget) already covers the
 * linked child's attendance and marks in natural language
 * (get_child_attendance / get_child_marks, with automatic multi-child
 * clarification). The workspace panels add the child's bio profile and
 * a form to message a teacher.
 */
export default function ParentPortal() {
  return (
    <PortalShell
      role="parent"
      workspace={
        <div className="grid gap-6 lg:grid-cols-2">
          <ChildProfilePanel />
          <MessageTeacherPanel role="parent" />
        </div>
      }
    />
  );
}
