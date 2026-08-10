import { createContext, useContext, useEffect, useState } from "react";
import { getEmail, getRole, getToken, logout as clearAuth } from "./auth";
import { jwtDecode } from "jwt-decode";


interface JwtPayload {
  exp: number;
}

interface User {
  email: string;
  role: string;
}

interface AuthContextType {
  user: User | null;
  isAuthenticated: boolean;
  loading: boolean;
  login: (email: string, role: string) => void;
  logout: () => void;
}

const AuthContext = createContext<AuthContextType>({
  user: null,
  isAuthenticated: false,
  loading: true,
  login: () => {},
  logout: () => {},
});

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  // Start "loading" so a page refresh doesn't bounce a valid session to
  // /login before we've had a chance to restore it from the stored token.
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const token = getToken();
    if (!token) {
      setLoading(false);
      return;
    }
    try {
      const decoded = jwtDecode<JwtPayload>(token);
      if (decoded.exp * 1000 < Date.now()) {
        clearAuth();
      } else {
        setUser({ email: getEmail() || "", role: getRole() || "" });
      }
    } catch {
      clearAuth();
    } finally {
      setLoading(false);
    }
  }, []);
  function login(email: string, role: string) {
    setUser({
        email,
        role,
    });
   }

  function logout() {
    clearAuth();
    setUser(null);
  }

  return (
    <AuthContext.Provider
        value={{
            user,
            isAuthenticated: !!user,
            loading,
            login,
            logout,
        }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  return useContext(AuthContext);
}