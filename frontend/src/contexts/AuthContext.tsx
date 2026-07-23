"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
} from "react";
import { useRouter } from "next/navigation";

import api, { TOKEN_KEY } from "../services/api";

export type CurrentUser = {
  id: string;
  email: string;
  role: string;
  organization_id: string;
  organization_name: string | null;
  organization_slug: string | null;
};

type AuthContextValue = {
  user: CurrentUser | null;
  // true until the initial "am I already logged in" check resolves -
  // pages should not decide to redirect to /login until this is false,
  // or a page reload would always briefly bounce a logged-in user.
  loading: boolean;
  login: (email: string, password: string) => Promise<void>;
  register: (
    email: string,
    password: string,
    organizationName: string
  ) => Promise<void>;
  logout: () => void;
};

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<CurrentUser | null>(null);
  // Lazily seeded from localStorage so the "no token at all" case
  // never needs a setState call inside the effect below - only the
  // "verifying an existing token" case does, and that one resolves
  // via a promise callback rather than synchronously in the effect
  // body.
  const [loading, setLoading] = useState(() => {
    if (typeof window === "undefined") return false;
    return Boolean(window.localStorage.getItem(TOKEN_KEY));
  });
  const router = useRouter();

  // Used by login()/register() after they already know a fresh token
  // exists - doesn't touch `loading`, since by that point the initial
  // mount-time check has long since resolved.
  const refreshCurrentUser = useCallback(async () => {
    try {
      const response = await api.get<CurrentUser>("/api/auth/me");
      setUser(response.data);
    } catch {
      setUser(null);
    }
  }, []);

  // Mount-time "am I already logged in" check. Defined inline inside
  // the effect (rather than routed through an outer useCallback used
  // elsewhere, as an earlier version of this did) so the eventual
  // setState calls read as local to this effect's own async flow.
  useEffect(() => {
    const token =
      typeof window !== "undefined"
        ? window.localStorage.getItem(TOKEN_KEY)
        : null;

    if (!token) {
      return;
    }

    async function verifyStoredToken() {
      try {
        const response = await api.get<CurrentUser>("/api/auth/me");
        setUser(response.data);
      } catch {
        setUser(null);
      } finally {
        setLoading(false);
      }
    }

    verifyStoredToken();
  }, []);

  async function login(email: string, password: string) {
    const response = await api.post<{ access_token: string }>(
      "/api/auth/login",
      { email, password }
    );

    window.localStorage.setItem(TOKEN_KEY, response.data.access_token);

    await refreshCurrentUser();

    router.push("/");
  }

  async function register(
    email: string,
    password: string,
    organizationName: string
  ) {
    await api.post("/api/auth/register", {
      email,
      password,
      organization_name: organizationName,
    });

    // Registration doesn't itself return a token - log in immediately
    // with the same credentials rather than sending the user to a
    // second form.
    await login(email, password);
  }

  function logout() {
    window.localStorage.removeItem(TOKEN_KEY);
    setUser(null);
    router.push("/login");
  }

  return (
    <AuthContext.Provider
      value={{ user, loading, login, register, logout }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const context = useContext(AuthContext);

  if (context === undefined) {
    throw new Error("useAuth must be used within an AuthProvider");
  }

  return context;
}
