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
  login: (email: string, role: string) => void;
  logout: () => void;
}

const AuthContext = createContext<AuthContextType>({
  user: null,
  isAuthenticated: false,
  login: () => {},
  logout: () => {},
});

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null);

  useEffect(() => {
    const token = getToken();

    if (!token) return;

    try {
        const decoded = jwtDecode<JwtPayload>(token);

        if (decoded.exp * 1000 < Date.now()) {
        clearAuth();
        return;
        }

        setUser({
        email: getEmail() || "",
        role: getRole() || "",
        });
    } catch {
        clearAuth();
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