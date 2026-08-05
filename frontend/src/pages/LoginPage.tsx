import { useState } from "react";
import { Navigate, useNavigate } from "react-router-dom";
import { login, saveToken } from "../auth/auth";
import { useAuth } from "../auth/AuthContext";

export default function LoginPage() {
  const navigate = useNavigate();
  const { isAuthenticated, login: setAuthUser } = useAuth();

  const [role, setRole] = useState<"admin" | "guest">("admin");

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  if (isAuthenticated) {
    return <Navigate to="/" replace />;
  }

  const handleRoleChange = (selectedRole: "admin" | "guest") => {
    setRole(selectedRole);

    if (selectedRole === "admin") {
      setEmail("admin@akash.ai");
    } else {
      setEmail("guest@akash.ai");
    }

    setPassword("");
  };

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();

    setLoading(true);
    setError("");

    try {
      const data = await login(email, password);

      if (data.role !== role) {
        setError(
            `No "${role}" exists.`
        );
        return;
      }

      saveToken(data);

      setAuthUser(data.email, data.role);

      navigate("/");
    } catch {
      setError("Invalid email or password");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-[#090E17] flex items-center justify-center px-4">

      <div className="w-full max-w-md rounded-2xl bg-[#111827] border border-gray-800 shadow-2xl p-8">

        <div className="text-center">

          <h1 className="text-4xl font-bold text-teal-400">
            Akash
          </h1>

          <p className="text-gray-400 mt-2">
            Research Platform
          </p>

          <h2 className="text-2xl font-semibold text-white mt-8">
            Welcome Back 
          </h2>


        </div>

        <form
          onSubmit={handleLogin}
          className="mt-8 space-y-5"
        >

          <div>

            <label className="text-gray-300 text-sm font-medium">
              Login As
            </label>

            <div className="flex gap-6 mt-3">

              <label className="flex items-center gap-2 text-gray-300 cursor-pointer">

                <input
                  type="radio"
                  checked={role === "admin"}
                  onChange={() => handleRoleChange("admin")}
                />

                Admin

              </label>

              <label className="flex items-center gap-2 text-gray-300 cursor-pointer">

                <input
                  type="radio"
                  checked={role === "guest"}
                  onChange={() => handleRoleChange("guest")}
                />

                Guest

              </label>

            </div>

          </div>

          <div>

            <label className="text-gray-300 text-sm font-medium">
              Email
            </label>

            <input
              type="email"
              value={email}
              placeholder={
                role === "admin"
                  ? "admin@akash.ai"
                  : "guest@akash.ai"
              }
              onChange={(e) => setEmail(e.target.value)}
              className="w-full mt-2 px-4 py-3 rounded-lg bg-[#1F2937] border border-gray-700 text-white outline-none focus:border-teal-400"
            />

          </div>

          <div>

            <label className="text-gray-300 text-sm font-medium">
              Password
            </label>

            <input
              type="password"
              value={password}
              placeholder="Enter password"
              onChange={(e) => setPassword(e.target.value)}
              className="w-full mt-2 px-4 py-3 rounded-lg bg-[#1F2937] border border-gray-700 text-white outline-none focus:border-teal-400"
            />

          </div>

          {error && (

            <div className="text-red-400 text-sm">
              {error}
            </div>

          )}

          <button
            type="submit"
            disabled={loading}
            className="w-full py-3 rounded-lg bg-teal-500 hover:bg-teal-600 transition text-white font-semibold"
          >
            {loading ? "Logging in..." : "Login"}
          </button>

          <div className="flex items-center my-2">

            <div className="flex-1 border-t border-gray-700"></div>

            <span className="px-3 text-gray-500 text-sm">
              OR
            </span>

            <div className="flex-1 border-t border-gray-700"></div>

          </div>

          <button
            type="button"
            disabled
            className="w-full py-3 rounded-lg border border-gray-700 text-gray-400 cursor-not-allowed"
          >
            Continue with Google
            <br />
            <span className="text-xs">
              Coming Soon
            </span>
          </button>

        </form>

      </div>

    </div>
  );
}