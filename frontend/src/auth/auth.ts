const API_URL = import.meta.env.VITE_API_URL;

export interface LoginResponse {
  token: string;
  role: string;
  email: string;
}

export async function login(email: string, password: string): Promise<LoginResponse> {
  const response = await fetch(`${API_URL}/login`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      email,
      password,
    }),
  });

  if (!response.ok) {
    throw new Error("Invalid email or password");
  }

  return response.json();
}

export function saveToken(data: LoginResponse) {
  localStorage.setItem("token", data.token);
  localStorage.setItem("role", data.role);
  localStorage.setItem("email", data.email);
}

export function logout() {
  localStorage.removeItem("token");
  localStorage.removeItem("role");
  localStorage.removeItem("email");
}

export function getToken() {
  return localStorage.getItem("token");
}

export function getRole() {
  return localStorage.getItem("role");
}

export function getEmail() {
  return localStorage.getItem("email");
}

export function isLoggedIn() {
  return !!localStorage.getItem("token");
}

export async function googleLogin(credential: string) {
  const response = await fetch(
    `${API_URL}/auth/google`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        credential,
      }),
    }
  );

  if (!response.ok) {
    throw new Error("Google login failed");
  }

  return response.json();
}