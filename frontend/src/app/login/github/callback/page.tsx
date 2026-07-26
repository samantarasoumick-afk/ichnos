"use client";

import Link from "next/link";
import { Suspense, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";

import { useAuth } from "../../../../contexts/AuthContext";
import { DataFeLogo } from "../../../../components/DataFeLogo";

function GithubCallbackInner() {
  const { loginWithGithubCode } = useAuth();
  const searchParams = useSearchParams();

  const [status, setStatus] = useState<"verifying" | "error">("verifying");
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  useEffect(() => {
    async function verify() {
      // GitHub redirects here with either `code`+`state` on success,
      // or `error`/`error_description` if the user declined the
      // consent screen or something else went wrong on GitHub's end.
      const oauthError = searchParams.get("error_description") || searchParams.get("error");
      const code = searchParams.get("code");
      const state = searchParams.get("state");

      if (oauthError) {
        setErrorMessage(oauthError);
        setStatus("error");
        return;
      }

      if (!code || !state) {
        setStatus("error");
        return;
      }

      try {
        await loginWithGithubCode(code, state);
      } catch (error) {
        console.error(error);

        const detail = (error as { response?: { data?: { detail?: string } } })?.response?.data
          ?.detail;

        setErrorMessage(detail ?? null);
        setStatus("error");
      }
    }

    verify();
    // Only run once, on mount - loginWithGithubCode navigates away on
    // success, and re-running on every render would re-submit the
    // (single-use) authorization code.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <main className="min-h-screen flex items-center justify-center bg-gray-100 p-6">
      <div className="w-full max-w-sm bg-white rounded-xl shadow p-8 text-center">
        <div className="mb-4 flex justify-center">
          <DataFeLogo size={30} textClassName="text-2xl font-bold" />
        </div>

        {status === "verifying" ? (
          <p className="text-sm text-gray-500">Signing you in with GitHub...</p>
        ) : (
          <div className="space-y-4">
            <div className="rounded border border-red-200 bg-red-50 p-4 text-sm text-red-700">
              {errorMessage ?? "GitHub sign-in didn't go through. Please try again."}
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

export default function GithubCallbackPage() {
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
      <GithubCallbackInner />
    </Suspense>
  );
}
