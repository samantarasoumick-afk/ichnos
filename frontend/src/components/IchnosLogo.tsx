// Ichnos (from Greek ίχνος - "trace" / "footprint" / "track") - the
// mark is an abstract trail of three connected points, matching the
// idea of tracing data's footprint across systems (lineage,
// classification, ownership) that the platform is built around.

export function IchnosMark({ size = 28 }: { size?: number }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 64 64"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      aria-hidden="true"
    >
      <rect width="64" height="64" rx="14" fill="#111827" />
      <path
        d="M14 46 Q20 30 32 32 Q44 34 50 18"
        stroke="#ffffff"
        strokeWidth="4"
        strokeLinecap="round"
      />
      <circle cx="14" cy="46" r="5" fill="#ffffff" />
      <circle cx="32" cy="32" r="5" fill="#ffffff" />
      <circle cx="50" cy="18" r="5" fill="#ffffff" />
    </svg>
  );
}

export function IchnosLogo({
  size = 28,
  textClassName = "font-semibold",
}: {
  size?: number;
  textClassName?: string;
}) {
  return (
    <span className="inline-flex items-center gap-2">
      <IchnosMark size={size} />
      <span className={textClassName}>Ichnos</span>
    </span>
  );
}
