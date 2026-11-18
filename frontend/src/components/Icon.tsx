// Small inline SVG icon set for the shell (DEC-061 / REV-0295: icon side menu, top bar, bottom navigation).
// Drawn on a 24px grid with `currentColor` strokes, so the icons follow the approved brand tokens and never
// need an external icon font or CDN. Icons are decorative (aria-hidden); every control carries its own text.

const PATHS = {
  home: "M3 11.5 12 4l9 7.5M5.5 9.5V20h5v-6h3v6h5V9.5",
  tasks: "M9 6h11M9 12h11M9 18h11M4 6l1 1 2-2M4 12l1 1 2-2M4 18l1 1 2-2",
  serial: "M4 6v12M7 6v12M10 6v12M14 6v12M17 6v12M20 6v12",
  order: "M8 4h8v3H8zM6 5.5H4.5V21h15V5.5H18M8 11h8M8 15h6",
  orderNew: "M6 3.5h8l4 4V21H6zM14 3.5V8h4M12 11v7M8.5 14.5h7",
  change: "M4 8h13l-3-3M20 16H7l3 3",
  product: "M5 8h14l-1 12H6zM9 8V6a3 3 0 0 1 6 0v2",
  customers: "M9 11a3.5 3.5 0 1 0 0-7 3.5 3.5 0 0 0 0 7M2.5 20a6.5 6.5 0 0 1 13 0M16 4.5a3.5 3.5 0 0 1 0 6.5M18 14a6 6 0 0 1 3.5 6",
  code: "M9 4 7 20M17 4l-2 16M4 9h17M3 15h17",
  documents: "M6 3.5h8l4 4V21H6zM14 3.5V8h4M9 13h6M9 17h6",
  org: "M10 3.5h4v4h-4zM4 16.5h4v4H4zM16 16.5h4v4h-4zM12 7.5v5M6 16.5v-4h12v4",
  security: "M12 3.5 19 6v6c0 4.5-3 7.5-7 8.5-4-1-7-4-7-8.5V6zM9 12l2 2 4-4",
  parameters: "M5 6h9M18 6h1M5 12h3M12 12h7M5 18h11M20 18h-1M14 4v4M8 10v4M16 16v4",
  ops: "M3 12h4l3-7 4 14 3-7h4",
  sessions: "M14.5 9.5a4 4 0 1 0-3.2 3.9L13 15h2v2h2v2h3v-3l-5.2-5.2a4 4 0 0 0-.3-1.3M8.5 9.5h.01",
  status: "M4 4.5h16v6H4zM4 13.5h16v6H4zM7.5 7.5h.01M7.5 16.5h.01",
  search: "M10.5 17a6.5 6.5 0 1 0 0-13 6.5 6.5 0 0 0 0 13M15.5 15.5 20 20",
  menu: "M4 6.5h16M4 12h16M4 17.5h16",
  pin: "M9 4h6l-1 5 3 3H7l3-3zM12 12v8",
  user: "M12 12a4 4 0 1 0 0-8 4 4 0 0 0 0 8M4.5 20.5a7.5 7.5 0 0 1 15 0",
  calendar: "M4.5 6h15v14h-15zM4.5 10h15M8.5 3.5v4M15.5 3.5v4",
  plus: "M12 5v14M5 12h14",
  chart: "M5 20V11M10 20V5M15 20v-7M20 20V8",
  more: "M6 12h.01M12 12h.01M18 12h.01",
  inbox: "M4 13.5 6.5 5h11l2.5 8.5V19h-16zM4 13.5h5l1 2h4l1-2h5",
  close: "M6 6l12 12M18 6 6 18",
  help: "M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18M9.5 9.5a2.5 2.5 0 1 1 3.5 2.3c-.6.3-1 .9-1 1.6v.6M12 17h.01",
  source: "M5 5.5c0-1.1 3.1-2 7-2s7 .9 7 2-3.1 2-7 2-7-.9-7-2M5 5.5v13c0 1.1 3.1 2 7 2s7-.9 7-2v-13M5 12c0 1.1 3.1 2 7 2s7-.9 7-2",
  download: "M12 4v11M7.5 10.5 12 15l4.5-4.5M5 19.5h14",
  clear: "M4 5h16l-6 7.5V19l-4 1.5v-8z",
} as const;

export type IconName = keyof typeof PATHS;

export function Icon({ name, size = 20, className }: { name: IconName; size?: number; className?: string }) {
  return (
    <svg
      className={className ? `icon ${className}` : "icon"}
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.8}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
    >
      <path d={PATHS[name]} />
    </svg>
  );
}
