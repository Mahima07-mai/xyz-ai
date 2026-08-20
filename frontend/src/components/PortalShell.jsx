import { roleMeta } from "../lib/roles";
import ChatWidget from "./ChatWidget";
import Header from "./Header";

/**
 * Layout shared by all four portal pages (see src/portals/). Each portal
 * file is a thin, explicitly-named wrapper around this shell so the repo
 * still shows the four distinct portals, while the actual header/chat
 * implementation is written once here and in ChatWidget -- never
 * duplicated four times.
 *
 * Phase 5 adds `workspace`: the structured, non-chat UI each role needs
 * for its own Flow (the interactive attendance/marks grids for Flow C/D,
 * messaging for Flow E, the principal dashboard for Flow F). These are
 * genuinely form/table-shaped workflows the directive calls out as
 * "Interactive UI Table" / "Grid Dashboard" -- a natural-language chat
 * turn is the wrong shape for filling in 30 students' attendance at
 * once, so they get real REST-backed panels here, rendered above the
 * chat widget rather than replacing it. Chat remains fully capable of
 * the same underlying actions in natural language (mark_attendance,
 * submit_exam_marks, ask_teacher, etc. in tools.py) -- this is a faster
 * *alternative* path for the same authorized backend calls, not a
 * separate one.
 */
export default function PortalShell({ role, workspace }) {
  const meta = roleMeta(role);
  return (
    <div className="min-h-screen bg-parchment-100">
      <Header meta={meta} />
      <main className="mx-auto max-w-6xl space-y-6 px-6 py-8">
        {workspace}
        <ChatWidget role={role} />
      </main>
    </div>
  );
}
