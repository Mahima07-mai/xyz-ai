import { Navigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";

const ROUTE_BY_ROLE = {
  student: "/student",
  parent: "/parent",
  teacher: "/staff",
  principal: "/management",
};

/**
 * Client-side route guard. This is a UX convenience only -- sending a
 * signed-in student to /management, for example, would render the
 * Management Portal's chat widget, but every /chat call it makes still
 * carries that student's verified JWT, so the backend's Authorization
 * layer (authz.py) would deny every principal-only tool call exactly as
 * if they'd typed the URL by hand. Real enforcement is server-side; this
 * component just avoids showing someone a portal shell that would only
 * ever produce denials.
 */
export default function ProtectedRoute({ role, children }) {
  const { session, isAuthenticated } = useAuth();

  if (!isAuthenticated) {
    return <Navigate to="/login" replace />;
  }
  if (session.role !== role) {
    return <Navigate to={ROUTE_BY_ROLE[session.role] || "/login"} replace />;
  }
  return children;
}
