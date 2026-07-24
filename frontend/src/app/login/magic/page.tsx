"use client";

import Link from "next/link";
import { Suspense, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";

import { useAuth } from "../../../contexts/AuthContext";
import { IchnosLogo } from "../../../components/IchnosLogo";

function MagicLoginInner() {
  const { loginWithMagicToken } = useAuth();
  const searchParams = useSearchParams();

  const [status, setStatus] = useState<"verifying" | "error">("verifying");

  useEffect(() => {
    async function verify() {
      const token = searchParams.get("token");

      if (!token) {
        setStatus("error");
        return;
      }

      try {
        await loginWithMagicToken(token);
      } catch (error) {
        console.error(error);
        setStatus("error");
      }
    }

    verify();
    // Only run once, on mount - loginWithMagicToken navigates away on
    // success, and re-running on every render would re-submit the
    // (single-use) token.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <main className="min-h-screen flex items-center justify-center bg-gray-100 p-6">
      <div className="w-full max-w-sm bg-white rounded-xl shadow p-8 text-center">
        <div className="mb-4 flex justify-center">
          <IchnosLogo size={30} textClassName="text-2xl font-bold" />
        </div>

        {status === "verifying" ? (
          <p className="text-sm text-gray-500">Signing you in...</p>
        ) : (
          <div className="space-y-4">
            <div className="rounded border border-red-200 bg-red-50 p-4 text-sm text-red-700">
              This login link is invalid or has expired.
            </div>
            <Link href="/login" className="text-sm text-black underline">
              Back to sign in
            </Link>
          </div>
        )}
      </div>
    </main>
  );
}

export default function MagicLoginPage() {
  return (
    <Suspense
      fallback={
        <main className="min-h-screen flex items-center justify-center bg-gray-100 p-6">
          <div className="w-full max-w-sm bg-white rounded-xl shadow p-8 text-center text-sm text-gray-500">
            Loading...
          </div>
        </main>
      }
    >
      <MagicLoginInner />
    </Suspense>
  );
}
