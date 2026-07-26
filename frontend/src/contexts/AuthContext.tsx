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
  // DataFe's own operator role, set directly in the database - not
  // grantable through any API. Gates the /platform dashboard link in
  // TopNav and the page itself; completely separate from `role`,
  // which is scoped to this user's own organization.
  is_platform_admin: boolean;
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
    organizationName: string,
    anonId?: string | null
  ) => Promise<void>;
  loginWithMagicToken: (token: string) => Promise<void>;
  loginWithGithubCode: (code: string, state: string) => Promise<void>;
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
    organizationName: string,
    anonId?: string | null
  ) {
    await api.post("/api/auth/register", {
      email,
      password,
      organization_name: organizationName,
      // Passed through from the marketing site's "Start free" link
      // (?anon_id=...) so this signup can be traced back to the
      // visit that led to it - see backend/app/services/
      // marketing_service.link_anon_id_to_signup. undefined/null
      // when someone lands on /register directly (no attribution,
      // still a completely normal signup).
      anon_id: anonId || undefined,
    });

    // Registration doesn't itself return a token - log in immediately
    // with the same credentials rather than sending the user to a
    // second form.
    await login(email, password);
  }

  async function loginWithMagicToken(token: string) {
    const response = await api.post<{ access_token: string }>(
      "/api/auth/magic-link/verify",
      { token }
    );

    window.localStorage.setItem(TOKEN_KEY, response.data.access_token);

    await refreshCurrentUser();

    router.push("/");
  }

  async function loginWithGithubCode(code: string, state: string) {
    // The state param is round-tripped from GitHub back to the
    // backend here purely so the backend can compare it against the
    // short-lived cookie it set when /oauth/github/start issued the
    // redirect (CSRF check) - the frontend itself doesn't need to
    // validate it, just pass it along.
    const response = await api.post<{ access_token: string }>(
      "/api/auth/oauth/github/callback",
      { code, state }
    );

    window.localStorage.setItem(TOKEN_KEY, response.data.access_token);

    await refreshCurrentUser();

    router.push("/");
  }

  function logout() {
    window.localStorage.removeItem(TOKEN_KEY);
    setUser(null);
    router.push("/login");
  }

  return (
    <AuthContext.Provider
      value={{
        user,
        loading,
        login,
        register,
        loginWithMagicToken,
        loginWithGithubCode,
        logout,
      }}
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
