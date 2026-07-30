// DataFe - "fe" (Spanish/Portuguese for "faith") + Data: have faith in
// your data. The mark is a governed seal: a navy disc (everything
// under governance) ringed by four capability-colored arcs -
// metadata intelligence (purple, top-right), lineage (blue,
// bottom-right), data quality (cyan, bottom-left), and governance
// (teal, top-left) - encircling a plain white square at the centre,
// the data asset itself. The logo *is* the legend for the product's
// four pillars, not a decorative mark. Below ~32px the four arcs
// blur together, so DataFeMark switches to a single cyan-ring
// fallback at small sizes rather than rendering illegible slivers.
// Same mark used on the marketing site (website/index.html) and the
// static public pages (favicon.svg, icon.svg, trust/privacy/terms/
// dpa.html) - kept in sync so the app and every surface show one
// logo, not several drifted copies.
//
// Deliberately cool-hued end to end (navy/purple/blue/cyan/teal) so
// none of the four capability colors collide with the reserved
// status palette (green/amber/red for pass/warn/fail) used elsewhere
// in the product - see docs/DataFe_Brand_Guidelines.docx.

const CAP = {
  metadata: "#8B5CF6",
  lineage: "#3B82F6",
  quality: "#06B6D4",
  governance: "#0D9488",
};

const CAP_DARK = {
  metadata: "#7C3AED",
  lineage: "#2563EB",
  quality: "#0891B2",
  governance: "#0D9488",
};

type MarkVariant = "light" | "dark";

export function DataFeMark({
  size = 28,
  variant = "light",
}: {
  size?: number;
  variant?: MarkVariant;
}) {
  const dark = variant === "dark";
  const disc = dark ? "#F1F5F9" : "#0F172A";
  const centre = dark ? "#0F172A" : "#fff";
  const cap = dark ? CAP_DARK : CAP;

  // Below ~32px the four arcs merge into a single band and the small
  // gaps between them fill in - rather than ship an illegible smear,
  // this size drops to one cyan ring at a heavier stroke weight, per
  // the reference color system's own sizing guidance.
  if (size < 32) {
    return (
      <svg
        width={size}
        height={size}
        viewBox="0 0 64 64"
        fill="none"
        xmlns="http://www.w3.org/2000/svg"
        aria-hidden="true"
      >
        <circle cx="32" cy="32" r="31" fill={disc} />
        <circle cx="32" cy="32" r="23" fill="none" stroke="#22D3EE" strokeWidth="6" />
        <rect x="23" y="23" width="18" height="18" rx="4.5" fill={centre} />
      </svg>
    );
  }

  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 64 64"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      aria-hidden="true"
    >
      <circle cx="32" cy="32" r="31" fill={disc} />
      <path d="M34.09 8.09 A24 24 0 0 1 55.91 29.91" fill="none" stroke={cap.metadata} strokeWidth="4" />
      <path d="M55.91 34.09 A24 24 0 0 1 34.09 55.91" fill="none" stroke={cap.lineage} strokeWidth="4" />
      <path d="M29.91 55.91 A24 24 0 0 1 8.09 34.09" fill="none" stroke={cap.quality} strokeWidth="4" />
      <path d="M8.09 29.91 A24 24 0 0 1 29.91 8.09" fill="none" stroke={cap.governance} strokeWidth="4" />
      <rect x="25" y="25" width="14" height="14" rx="3.5" fill={centre} />
    </svg>
  );
}

export function DataFeLogo({
  size = 28,
  textClassName = "font-semibold",
  variant = "light",
}: {
  size?: number;
  textClassName?: string;
  variant?: MarkVariant;
}) {
  const dark = variant === "dark";

  return (
    <span className="inline-flex items-center gap-2">
      <DataFeMark size={size} variant={variant} />
      <span className={textClassName}>
        <span style={{ color: dark ? "#fff" : "#0F172A" }}>Data</span>
        <span style={{ color: dark ? "#5EEAD4" : "#0D9488" }}>Fe</span>
      </span>
    </span>
  );
}
