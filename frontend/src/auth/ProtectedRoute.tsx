import { Navigate } from "react-router-dom";
import { useAuth } from "./AuthContext";

interface Props {
  children: JSX.Element;
}

export default function ProtectedRoute({ children }: Props) {
  const { isAuthenticated, loading } = useAuth();

  // Wait for the token check to finish — otherwise a refresh redirects a
  // logged-in user to /login before the session is restored.
  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center text-gray-500 text-sm">
        Loading…
      </div>
    );
  }

  if (!isAuthenticated) {
    return <Navigate to="/login" replace />;
  }

  return children;
}