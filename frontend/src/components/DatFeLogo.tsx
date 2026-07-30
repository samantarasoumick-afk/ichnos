// DatFe - "fe" (Spanish/Portuguese for "faith") + Data: have faith in
// your data. The mark is a governed seal, deliberately monochrome
// rather than color-coded: a solid disc (everything under
// governance) ringed by a broken circle - four short arcs with gaps
// at the cardinal points, reading as a reticle/target lock rather
// than a plain ring - encircling a plain rounded square at the
// centre, the data asset itself, sighted and accounted for. Below
// ~32px the four arcs blur together, so DatFeMark switches to a
// single solid-ring fallback at small sizes rather than rendering
// illegible slivers.
// Same mark used on the marketing site (website/index.html) and the
// static public pages (favicon.svg, icon.svg, trust/privacy/terms/
// dpa.html) - kept in sync so the app and every surface show one
// logo, not several drifted copies.

type MarkVariant = "light" | "dark";

export function DatFeMark({
  size = 28,
  variant = "light",
}: {
  size?: number;
  variant?: MarkVariant;
}) {
  const dark = variant === "dark";
  const ink = dark ? "#F8FAFC" : "#0F172A";
  const centre = dark ? "#0F172A" : "#fff";

  // Below ~32px the four arcs merge into a single band and the small
  // gaps between them fill in - rather than ship an illegible smear,
  // this size drops to one solid ring at a heavier stroke weight.
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
        <circle cx="32" cy="32" r="31" fill={ink} />
        <circle cx="32" cy="32" r="23" fill="none" stroke={centre} strokeWidth="6" />
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
      <circle cx="32" cy="32" r="31" fill={ink} />
      <path d="M34.09 8.09 A24 24 0 0 1 55.91 29.91" fill="none" stroke={centre} strokeWidth="4" />
      <path d="M55.91 34.09 A24 24 0 0 1 34.09 55.91" fill="none" stroke={centre} strokeWidth="4" />
      <path d="M29.91 55.91 A24 24 0 0 1 8.09 34.09" fill="none" stroke={centre} strokeWidth="4" />
      <path d="M8.09 29.91 A24 24 0 0 1 29.91 8.09" fill="none" stroke={centre} strokeWidth="4" />
      <rect x="25" y="25" width="14" height="14" rx="3.5" fill={centre} />
    </svg>
  );
}

export function DatFeLogo({
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
      <DatFeMark size={size} variant={variant} />
      <span className={textClassName} style={{ color: dark ? "#fff" : "#0F172A" }}>
        DatFe
      </span>
    </span>
  );
}
