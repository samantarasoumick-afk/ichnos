// Ichnos (from Greek ίχνος - "trace" / "footprint" / "track") - the
// mark is a beacon/signal: two arcs broadcasting outward from a point,
// tracing down into a grounded stem, matching the idea of tracing
// data's footprint - and picking up its trail - across systems
// (lineage, classification, ownership). Same mark used on the
// marketing site (website/index.html) - kept in sync so the app and
// the site show one logo, not two.

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
      <g transform="translate(8, 8) scale(2)">
        <path
          d="M6.5 8.2C7 5.8 9.2 4 11.8 4s4.8 1.8 5.3 4.2"
          stroke="#8b7cf6"
          strokeWidth="1.5"
          strokeLinecap="round"
          opacity="0.5"
        />
        <path
          d="M8.7 9.6c.4-1.6 1.7-2.7 3.1-2.7s2.7 1.1 3.1 2.7"
          stroke="#8b7cf6"
          strokeWidth="1.5"
          strokeLinecap="round"
          opacity="0.85"
        />
        <circle cx="11.8" cy="11.6" r="1.9" fill="#8b7cf6" />
        <rect x="10.6" y="13" width="2.4" height="6.2" rx="1.2" fill="#8b7cf6" />
      </g>
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
