"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";

import { useAuth } from "../contexts/AuthContext";

/**
 * Redirects to /login if there's no authenticated user, once the
 * initial auth check has finished. Use at the top of any page that
 * requires a logged-in user; while `loading` is true or a redirect is
 * about to happen, render nothing (or a loading state) rather than
 * the protected content.
 */
export function useRequireAuth() {
  const { user, loading } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (!loading && !user) {
      router.push("/login");
    }
  }, [loading, user, router]);

  return { user, loading };
}
