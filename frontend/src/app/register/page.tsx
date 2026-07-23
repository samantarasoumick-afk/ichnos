"use client";

import Link from "next/link";
import { useState } from "react";

import { useAuth } from "../../contexts/AuthContext";

export default function RegisterPage() {
  const { register } = useAuth();

  const [organizationName, setOrganizationName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();

    setErrorMessage(null);
    setLoading(true);

    try {
      await register(email, password, organizationName);
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
        <h1 className="text-2xl font-bold mb-1">Create your organization</h1>
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
