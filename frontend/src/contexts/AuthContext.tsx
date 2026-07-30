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
import type { UserRole } from "../types/metadata";

export type CurrentUser = {
  id: string;
  email: string;
  role: string;
  organization_id: string;
  organization_name: string | null;
  organization_slug: string | null;
  // DatFe's own operator role, set directly in the database - not
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
  // "Preview as" - lets an actual Admin see the app the way a Steward,
  // Data Owner, or Viewer would, without touching their real account
  // role. Purely a frontend display override: every mutating request
  // still goes through the backend under the real account, which
  // enforces the real role regardless of what's being previewed here.
  // previewRole only ever takes effect when the real user is an admin
  // (setPreviewRole no-ops otherwise) - effectiveRole is what every
  // role-gated bit of UI in the app should read instead of user.role.
  previewRole: UserRole | null;
  setPreviewRole: (role: UserRole | null) => void;
  effectiveRole: UserRole | null;
  isPreviewing: boolean;
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
  const [previewRole, setPreviewRoleState] = useState<UserRole | null>(null);
  const router = useRouter();

  // No effect needed to guard a stale previewRole after the real
  // account stops being admin (role downgrade, different account) -
  // effectiveRole below already ignores previewRole unless
  // user?.role === "admin", so a stale value in memory here never
  // actually takes effect anywhere; it just gets cleared for real on
  // the next logout() or setPreviewRole(null) call.
  const setPreviewRole = useCallback(
    (role: UserRole | null) => {
      if (user?.role !== "admin") return;
      setPreviewRoleState(role);
    },
    [user]
  );

  const effectiveRole: UserRole | null =
    user?.role === "admin" && previewRole ? previewRole : (user?.role as UserRole | undefined) ?? null;

  const isPreviewing = user?.role === "admin" && previewRole !== null && previewRole !== "admin";

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
    setPreviewRoleState(null);
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
        previewRole,
        setPreviewRole,
        effectiveRole,
        isPreviewing,
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
