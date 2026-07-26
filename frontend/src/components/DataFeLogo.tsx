// DataFe - "fe" (Spanish/Portuguese for "faith") + Data: have faith in
// your data. The mark is an element-mark: "Fe" (iron's own periodic
// symbol) set inside a hexagon, echoing a periodic-table tile -
// backbone/element branding for a data backbone. Dark squircle
// (#14121F) + copper (#C17845) accent. Same mark used on the
// marketing site (website/index.html) - kept in sync so the app and
// the site show one logo, not two.

export function DataFeMark({ size = 28 }: { size?: number }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 64 64"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      aria-hidden="true"
    >
      <rect width="64" height="64" rx="15" fill="#14121F" />
      <polygon
        points="32,16.5 45.5,24.7 45.5,41.3 32,49.5 18.5,41.3 18.5,24.7"
        stroke="#C17845"
        strokeWidth="2.3"
        fill="none"
        strokeLinejoin="round"
      />
      <text
        x="32"
        y="37.5"
        textAnchor="middle"
        fontFamily="Arial, sans-serif"
        fontWeight="700"
        fontSize="14.5"
        fill="#C17845"
      >
        Fe
      </text>
    </svg>
  );
}

export function DataFeLogo({
  size = 28,
  textClassName = "font-semibold",
}: {
  size?: number;
  textClassName?: string;
}) {
  return (
    <span className="inline-flex items-center gap-2">
      <DataFeMark size={size} />
      <span className={textClassName}>DataFe</span>
    </span>
  );
}
