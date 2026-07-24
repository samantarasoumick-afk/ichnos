"use client";

import Link from "next/link";
import { useState } from "react";

import { useAuth } from "../../contexts/AuthContext";
import { IchnosLogo } from "../../components/IchnosLogo";
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
          <IchnosLogo size={30} textClassName="text-2xl font-bold" />
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
