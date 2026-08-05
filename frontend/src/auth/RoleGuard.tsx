import { Navigate } from "react-router-dom";
import { useAuth } from "./AuthContext";

interface RoleGuardProps {
  allowedRoles: string[];
  children: JSX.Element;
}

export default function RoleGuard({
  allowedRoles,
  children,
}: RoleGuardProps) {
  const { user } = useAuth();

  if (!user) {
    return <Navigate to="/login" replace />;
  }

  if (!allowedRoles.includes(user.role)) {
    return <Navigate to="/" replace />;
  }

  return children;
}