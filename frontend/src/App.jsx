import { Navigate, Route, Routes } from "react-router-dom";
import { useAuth } from "./context/AuthContext";
import ProtectedRoute from "./components/ProtectedRoute";
import LoginPortal from "./portals/LoginPortal";
import StudentPortal from "./portals/StudentPortal";
import ParentPortal from "./portals/ParentPortal";
import StaffPortal from "./portals/StaffPortal";
import ManagementPortal from "./portals/ManagementPortal";

const ROUTE_BY_ROLE = {
  student: "/student",
  parent: "/parent",
  teacher: "/staff",
  principal: "/management",
};

function RootRedirect() {
  const { session, isAuthenticated } = useAuth();
  const target = isAuthenticated ? ROUTE_BY_ROLE[session.role] || "/login" : "/login";
  return <Navigate to={target} replace />;
}

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<RootRedirect />} />
      <Route path="/login" element={<LoginPortal />} />
      <Route
        path="/student"
        element={
          <ProtectedRoute role="student">
            <StudentPortal />
          </ProtectedRoute>
        }
      />
      <Route
        path="/parent"
        element={
          <ProtectedRoute role="parent">
            <ParentPortal />
          </ProtectedRoute>
        }
      />
      <Route
        path="/staff"
        element={
          <ProtectedRoute role="teacher">
            <StaffPortal />
          </ProtectedRoute>
        }
      />
      <Route
        path="/management"
        element={
          <ProtectedRoute role="principal">
            <ManagementPortal />
          </ProtectedRoute>
        }
      />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
