import PortalShell from "../components/PortalShell";
import PrincipalDashboard from "../components/workspace/PrincipalDashboard";

/**
 * Management Portal -- the principal-facing portal. Backend role key is
 * "principal" (see backend/app/model.py AuthPrincipal).
 *
 * PrincipalDashboard covers Flow F: the class/section summary grid with
 * key metric cards, subject-based teacher search, and student/teacher
 * bio lookups -- the directive's "Interactive, visually rich Grid
 * Dashboard" requirement. School-wide attendance analytics and any
 * AI-synthesized report (failure breakdowns, absentee patterns) stay
 * conversational, via chat below.
 */
export default function ManagementPortal() {
  return <PortalShell role="principal" workspace={<PrincipalDashboard />} />;
}
