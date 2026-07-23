"use client";

import Link from "next/link";

import { useAuth } from "../contexts/AuthContext";
import { IchnosLogo } from "./IchnosLogo";

export default function TopNav() {
  const { user, logout } = useAuth();

  return (
    <div className="mb-6 flex flex-wrap items-center justify-between gap-3 rounded-xl bg-white px-5 py-3 shadow">
      <div className="flex items-center gap-4">
        <Link href="/">
          <IchnosLogo size={26} />
        </Link>

        <Link href="/lineage" className="text-sm text-gray-600 hover:text-black">
          Lineage
        </Link>

        <Link href="/ask" className="text-sm text-gray-600 hover:text-black">
          Ask
        </Link>

        <Link href="/discussions" className="text-sm text-gray-600 hover:text-black">
          Discussions
        </Link>

        <Link href="/governance" className="text-sm text-gray-600 hover:text-black">
          Governance
        </Link>

        <Link href="/glossary" className="text-sm text-gray-600 hover:text-black">
          Glossary
        </Link>

        <Link href="/processes" className="text-sm text-gray-600 hover:text-black">
          Processes
        </Link>

        <Link href="/privacy" className="text-sm text-gray-600 hover:text-black">
          Privacy
        </Link>

        <Link href="/audit-log" className="text-sm text-gray-600 hover:text-black">
          Audit Log
        </Link>

        <Link href="/team" className="text-sm text-gray-600 hover:text-black">
          Team
        </Link>
      </div>

      {user && (
        <div className="flex items-center gap-3 text-sm text-gray-600">
          <span>
            {user.organization_name} &middot; {user.email}
          </span>
          <span className="rounded-full bg-gray-100 px-2 py-0.5 text-xs uppercase text-gray-700">
            {user.role.replace("_", " ")}
          </span>
          <button
            onClick={logout}
            className="rounded-lg border px-3 py-1.5 text-sm hover:bg-gray-50"
          >
            Log out
          </button>
        </div>
      )}
    </div>
  );
}
