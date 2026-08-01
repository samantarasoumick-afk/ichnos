"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useRef, useState } from "react";

import { useAuth } from "../contexts/AuthContext";
import type { UserRole } from "../types/metadata";
import { DatFeLogo } from "./DatFeLogo";
import GlobalSearch from "./GlobalSearch";

type NavItem = {
  href: string;
  label: string;
};

// Admin-only "view as" - lets an admin see the app the way each other
// role would, without changing their real account. "viewer" is labeled
// Audience View here since that's the term non-technical stakeholders
// (the actual audience for a Viewer seat) use for it.
const PREVIEW_ROLE_OPTIONS: { value: UserRole; label: string }[] = [
  { value: "admin", label: "Admin View" },
  { value: "steward", label: "Steward View" },
  { value: "data_owner", label: "Owner View" },
  { value: "viewer", label: "Audience View" },
];

// Ecosystem/Lineage/Data Quality are grouped the same way Governance's
// six items already are - three flat top-level links read as three
// competing destinations, but as a group they're really one answer to
// "where does my data live and can I trust it."
const CATALOG_ITEMS: NavItem[] = [
  { href: "/ecosystem", label: "Ecosystem" },
  { href: "/lineage", label: "Lineage" },
  { href: "/data-quality", label: "Data Quality" },
];

const GOVERNANCE_ITEMS: NavItem[] = [
  { href: "/governance", label: "Overview" },
  { href: "/glossary", label: "Glossary" },
  { href: "/processes", label: "Processes" },
  { href: "/contracts", label: "Contracts" },
  { href: "/risks", label: "Risks & Controls" },
  { href: "/privacy", label: "Privacy" },
];

const ADMIN_ITEMS: NavItem[] = [
  { href: "/audit-log", label: "Audit Log" },
  { href: "/team", label: "Team" },
  { href: "/settings/billing", label: "Billing" },
];

// Unlike the items above, /api/query-log is actually enforced
// admin-only on the backend (it surfaces the literal text people
// searched for, not just an activity trail) - so only show the link
// to users who can actually open it, rather than let non-admins hit a
// dead end.
const ADMIN_ONLY_ITEMS: NavItem[] = [
  { href: "/query-log", label: "Search Insights" },
];

function NavDropdown({
  label,
  items,
  pathname,
}: {
  label: string;
  items: NavItem[];
  pathname: string;
}) {
  const [open, setOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  const isActive = items.some((item) => pathname.startsWith(item.href));

  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(event.target as Node)) {
        setOpen(false);
      }
    }

    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  return (
    <div className="relative" ref={containerRef}>
      <button
        type="button"
        onClick={() => setOpen((prev) => !prev)}
        className={`flex items-center gap-1 text-sm hover:text-black ${
          isActive ? "font-semibold text-black" : "text-gray-600"
        }`}
      >
        {label}
        <span className="text-[10px]">{open ? "▲" : "▼"}</span>
      </button>

      {open && (
        <div className="absolute left-0 top-full z-10 mt-2 w-48 rounded-lg border bg-white py-1 shadow-lg">
          {items.map((item) => (
            <Link
              key={item.href}
              href={item.href}
              onClick={() => setOpen(false)}
              className={`block px-4 py-2 text-sm hover:bg-gray-50 ${
                pathname.startsWith(item.href) ? "font-semibold text-black" : "text-gray-600"
              }`}
            >
              {item.label}
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}

export default function TopNav() {
  const { user, logout, effectiveRole, isPreviewing, setPreviewRole } = useAuth();
  const pathname = usePathname() ?? "";

  function linkClasses(href: string) {
    const active = pathname.startsWith(href);
    return `text-sm hover:text-black ${active ? "font-semibold text-black" : "text-gray-600"}`;
  }

  return (
    <>
    {isPreviewing && (
      <div className="mb-3 flex items-center justify-between rounded-xl border border-amber-300 bg-amber-50 px-4 py-2 text-sm text-amber-800">
        <span>
          Previewing as <strong>{PREVIEW_ROLE_OPTIONS.find((o) => o.value === effectiveRole)?.label}</strong> - this is
          how the app looks to that role. Your real Admin account and permissions are unchanged.
        </span>
        <button
          type="button"
          onClick={() => setPreviewRole(null)}
          className="ml-4 shrink-0 rounded-lg border border-amber-300 bg-white px-3 py-1 text-xs font-medium hover:bg-amber-100"
        >
          Exit preview
        </button>
      </div>
    )}
    <div className="mb-6 flex flex-wrap items-center justify-between gap-3 rounded-xl bg-white px-5 py-3 shadow">
      <div className="flex items-center gap-5">
        <Link href="/">
          <DatFeLogo size={32} />
        </Link>

        <NavDropdown label="Catalog" items={CATALOG_ITEMS} pathname={pathname} />

        <NavDropdown label="Governance" items={GOVERNANCE_ITEMS} pathname={pathname} />

        <Link href="/ask" className={linkClasses("/ask")}>
          Ask&apos;Fe&apos;
        </Link>

        <Link href="/discussions" className={linkClasses("/discussions")}>
          Discussions
        </Link>

        <NavDropdown
          label="Admin"
          items={effectiveRole === "admin" ? [...ADMIN_ITEMS, ...ADMIN_ONLY_ITEMS] : ADMIN_ITEMS}
          pathname={pathname}
        />

        {/* DatFe's own operator role (see CurrentUser.is_platform_admin's
            comment) - completely separate from the org-scoped Admin
            dropdown above, so it's a distinct link rather than folded
            into it. */}
        {user?.is_platform_admin && (
          <Link
            href="/platform"
            className={`${linkClasses("/platform")} rounded-full bg-[#0F172A] px-2.5 py-1 !text-white`}
          >
            Platform
          </Link>
        )}
      </div>

      {user && <GlobalSearch />}

      {user && (
        <div className="flex items-center gap-3 text-sm text-gray-600">
          <span>
            {user.organization_name} &middot; {user.email}
          </span>

          {user.role === "admin" && (
            <select
              value={effectiveRole ?? "admin"}
              onChange={(event) => {
                const next = event.target.value as UserRole;
                setPreviewRole(next === "admin" ? null : next);
              }}
              title="Preview the app as a different role - your real Admin account and permissions are unchanged."
              className={`rounded-lg border px-2 py-1 text-xs ${
                isPreviewing ? "border-amber-400 bg-amber-50 text-amber-800" : "text-gray-600"
              }`}
            >
              {PREVIEW_ROLE_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          )}

          <span
            className={`rounded-full px-2 py-0.5 text-xs uppercase ${
              isPreviewing ? "bg-amber-100 text-amber-800" : "bg-gray-100 text-gray-700"
            }`}
          >
            {(effectiveRole ?? user.role).replace("_", " ")}
            {isPreviewing ? " · preview" : ""}
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
    </>
  );
}
