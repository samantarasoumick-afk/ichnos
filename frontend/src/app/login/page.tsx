"use client";

import Link from "next/link";
import { useState } from "react";

import { useAuth } from "../../contexts/AuthContext";
import { DataFeLogo } from "../../components/DataFeLogo";
import api from "../../services/api";

export default function LoginPage() {
  const { login } = useAuth();

  const [mode, setMode] = useState<"password" | "magic-link">("password");

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const [magicLinkSent, setMagicLinkSent] = useState(false);

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();

    setErrorMessage(null);
    setLoading(true);

    try {
      await login(email, password);
    } catch (error) {
      console.error(error);

      const status = (error as { response?: { status?: number } })?.response?.status;
      const detail = (error as { response?: { data?: { detail?: string } } })?.response?.data
        ?.detail;

      if (status === 429 && detail) {
        setErrorMessage(detail);
      } else {
        setErrorMessage("Invalid email or password.");
      }
    } finally {
      setLoading(false);
    }
  }

  async function handleMagicLinkSubmit(event: React.FormEvent) {
    event.preventDefault();

    setErrorMessage(null);
    setLoading(true);

    try {
      await api.post("/api/auth/magic-link/request", { email });
      setMagicLinkSent(true);
    } catch (error) {
      console.error(error);
      setErrorMessage("Something went wrong sending that link. Try again.");
    } finally {
      setLoading(false);
    }
  }

  function switchMode(next: "password" | "magic-link") {
    setMode(next);
    setErrorMessage(null);
    setMagicLinkSent(false);
  }

  return (
    <main className="min-h-screen flex items-center justify-center bg-gray-100 p-6">
      <div className="w-full max-w-sm bg-white rounded-xl shadow p-8">
        <div className="mb-1">
          <DataFeLogo size={30} textClassName="text-2xl font-bold" />
        </div>
        <p className="text-sm text-gray-500 mb-6">Sign in to continue</p>

        {mode === "password" ? (
          <form onSubmit={handleSubmit} className="space-y-4">
            <input
              type="email"
              required
              placeholder="Email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="w-full border p-3 rounded"
            />

            <input
              type="password"
              required
              placeholder="Password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full border p-3 rounded"
            />

            {errorMessage && (
              <div className="rounded border border-red-200 bg-red-50 p-3 text-sm text-red-700">
                {errorMessage}
              </div>
            )}

            <button
              type="submit"
              disabled={loading}
              className="w-full bg-black text-white px-6 py-3 rounded-xl disabled:opacity-50"
            >
              {loading ? "Signing in..." : "Sign in"}
            </button>

            <button
              type="button"
              onClick={() => switchMode("magic-link")}
              className="w-full text-center text-sm text-gray-500 underline hover:text-black"
            >
              Email me a login link instead
            </button>

            <div className="flex items-center gap-3 text-xs text-gray-400">
              <div className="h-px flex-1 bg-gray-200" />
              or
              <div className="h-px flex-1 bg-gray-200" />
            </div>

            {/* Plain link, not a JS click handler - this needs to be a
                real page navigation so the browser follows the
                backend's redirect straight to GitHub's consent
                screen (an XHR/fetch can't do that). */}
            <a
              href="/backend/api/auth/oauth/github/start"
              className="w-full flex items-center justify-center gap-2 border px-6 py-3 rounded-xl hover:bg-gray-50"
            >
              <svg
                width="18"
                height="18"
                viewBox="0 0 16 16"
                fill="currentColor"
                aria-hidden="true"
              >
                <path d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.01 8.01 0 0016 8c0-4.42-3.58-8-8-8z" />
              </svg>
              Continue with GitHub
            </a>
          </form>
        ) : magicLinkSent ? (
          <div className="space-y-4">
            <div className="rounded border border-green-200 bg-green-50 p-4 text-sm text-green-800">
              If an account exists for <span className="font-medium">{email}</span>, we&apos;ve
              sent a login link. It expires in 15 minutes - check your inbox (and the backend
              logs, if this instance hasn&apos;t got real email sending configured yet).
            </div>
            <button
              type="button"
              onClick={() => switchMode("password")}
              className="w-full text-center text-sm text-gray-500 underline hover:text-black"
            >
              Back to password sign-in
            </button>
          </div>
        ) : (
          <form onSubmit={handleMagicLinkSubmit} className="space-y-4">
            <input
              type="email"
              required
              placeholder="Email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="w-full border p-3 rounded"
            />

            {errorMessage && (
              <div className="rounded border border-red-200 bg-red-50 p-3 text-sm text-red-700">
                {errorMessage}
              </div>
            )}

            <button
              type="submit"
              disabled={loading}
              className="w-full bg-black text-white px-6 py-3 rounded-xl disabled:opacity-50"
            >
              {loading ? "Sending..." : "Send login link"}
            </button>

            <button
              type="button"
              onClick={() => switchMode("password")}
              className="w-full text-center text-sm text-gray-500 underline hover:text-black"
            >
              Use a password instead
            </button>
          </form>
        )}

        <p className="text-sm text-gray-500 mt-6">
          No account yet?{" "}
          <Link href="/register" className="text-black underline">
            Create one
          </Link>
        </p>
      </div>
    </main>
  );
}
