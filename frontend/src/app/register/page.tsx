"use client";

import Link from "next/link";
import { useState } from "react";

import { DatFeLogo } from "../../components/DatFeLogo";
import { useAuth } from "../../contexts/AuthContext";

export default function RegisterPage() {
  const { register } = useAuth();

  const [organizationName, setOrganizationName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  // Read once, lazily, rather than via useSearchParams() - see
  // discussions/page.tsx's typeFilter for why (a Suspense boundary
  // requirement for what's just a one-off, non-reactive read).
  // Present when this link came from the marketing site's tracking
  // snippet (website/index.html) - absent for anyone who reached
  // /register directly, which is fine.
  const [anonId] = useState<string | null>(() => {
    if (typeof window === "undefined") return null;
    return new URLSearchParams(window.location.search).get("anon_id");
  });

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();

    setErrorMessage(null);
    setLoading(true);

    try {
      await register(email, password, organizationName, anonId);
    } catch (error) {
      const detail =
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        (error as any)?.response?.data?.detail ??
        "Could not create your account. Please try again.";
      console.error(error);
      setErrorMessage(String(detail));
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="min-h-screen flex items-center justify-center bg-gray-100 p-6">
      <div className="w-full max-w-sm bg-white rounded-xl shadow p-8">
        <div className="mb-1">
          <DatFeLogo size={36} textClassName="text-2xl font-bold" />
        </div>
        <p className="text-sm text-gray-500 mb-1">Create your organization</p>
        <p className="text-sm text-gray-500 mb-6">
          You&apos;ll be the admin of a brand-new organization.
        </p>

        <form onSubmit={handleSubmit} className="space-y-4">
          <input
            type="text"
            required
            placeholder="Organization name"
            value={organizationName}
            onChange={(e) => setOrganizationName(e.target.value)}
            className="w-full border p-3 rounded"
          />

          <input
            type="email"
            required
            placeholder="Work email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            className="w-full border p-3 rounded"
          />

          <input
            type="password"
            required
            minLength={8}
            placeholder="Password (min. 8 characters)"
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
            {loading ? "Creating account..." : "Create account"}
          </button>
        </form>

        <p className="text-sm text-gray-500 mt-6">
          Already have an account?{" "}
          <Link href="/login" className="text-black underline">
            Sign in
          </Link>
        </p>
      </div>
    </main>
  );
}
