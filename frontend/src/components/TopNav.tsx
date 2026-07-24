"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useRef, useState } from "react";

import { useAuth } from "../contexts/AuthContext";
import { IchnosLogo } from "./IchnosLogo";

type NavItem = {
  href: string;
  label: string;
};

const GOVERNANCE_ITEMS: NavItem[] = [
  { href: "/governance", label: "Overview" },
  { href: "/glossary", label: "Glossary" },
  { href: "/processes", label: "Processes" },
  { href: "/risks", label: "Risks & Controls" },
  { href: "/privacy", label: "Privacy" },
];

const ADMIN_ITEMS: NavItem[] = [
  { href: "/audit-log", label: "Audit Log" },
  { href: "/team", label: "Team" },
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
  const { user, logout } = useAuth();
  const pathname = usePathname() ?? "";

  function linkClasses(href: string) {
    const active = pathname.startsWith(href);
    return `text-sm hover:text-black ${active ? "font-semibold text-black" : "text-gray-600"}`;
  }

  return (
    <div className="mb-6 flex flex-wrap items-center justify-between gap-3 rounded-xl bg-white px-5 py-3 shadow">
      <div className="flex items-center gap-5">
        <Link href="/">
          <IchnosLogo size={26} />
        </Link>

        <Link href="/lineage" className={linkClasses("/lineage")}>
          Lineage
        </Link>

        <Link href="/data-quality" className={linkClasses("/data-quality")}>
          Data Quality
        </Link>

        <Link href="/ask" className={linkClasses("/ask")}>
          Ask
        </Link>

        <Link href="/discussions" className={linkClasses("/discussions")}>
          Discussions
        </Link>

        <NavDropdown label="Governance" items={GOVERNANCE_ITEMS} pathname={pathname} />

        <NavDropdown label="Admin" items={ADMIN_ITEMS} pathname={pathname} />
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
