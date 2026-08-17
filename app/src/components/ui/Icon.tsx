// Handoff › Assets — "All other iconography is inline SVG, Feather/Lucide
// style: viewBox 0 0 24 24, fill none, stroke currentColor, stroke-width 2–2.6,
// round caps/joins, rendered 12–22px." No icon fonts, no raster icons, no emoji.
//
// The path set is transcribed from the prototype's `P` table plus the handful
// of extra glyphs the screens need. Reach for `lucide-react` only where the
// glyph matches Feather exactly; otherwise add a path here.

import type { SVGProps } from "react";
import { cn } from "@/lib/cn";

export const ICON_PATHS = {
  grid: '<rect x="3" y="3" width="7" height="8" rx="2"/><rect x="14" y="3" width="7" height="5" rx="2"/><rect x="14" y="11" width="7" height="10" rx="2"/><rect x="3" y="14" width="7" height="7" rx="2"/>',
  folder:
    '<path d="M3 7.5A2.5 2.5 0 0 1 5.5 5h3.2l2 2.2h7.8A2.5 2.5 0 0 1 21 9.7v7.8A2.5 2.5 0 0 1 18.5 20h-13A2.5 2.5 0 0 1 3 17.5z"/>',
  ticket:
    '<path d="M4 9V7.5A2.5 2.5 0 0 1 6.5 5h11A2.5 2.5 0 0 1 20 7.5V9a2.4 2.4 0 0 0 0 6v1.5A2.5 2.5 0 0 1 17.5 19h-11A2.5 2.5 0 0 1 4 16.5V15a2.4 2.4 0 0 0 0-6z"/><path d="M12 8v8" stroke-dasharray="2 3"/>',
  book: '<path d="M4 5.6A2.6 2.6 0 0 1 6.6 3H20v14.5H6.6A2.6 2.6 0 0 0 4 20.1z"/><path d="M4 5.6v14.5"/><path d="M8 7.5h7"/>',
  spark: '<path d="M12 2l2.5 6.1L21 10l-6.5 1.9L12 18l-2.5-6.1L3 10l6.5-1.9z"/>',
  shield:
    '<path d="M12 3l8 3v6c0 4.6-3.3 8-8 9-4.7-1-8-4.4-8-9V6z"/><path d="M9.2 12.2l2 2 3.6-3.9"/>',
  users:
    '<circle cx="9" cy="8" r="3.4"/><path d="M3 20c0-3.2 2.7-5.5 6-5.5s6 2.3 6 5.5"/><path d="M16.5 5.2a3.4 3.4 0 0 1 0 6.4M17.5 14.8c2.2.6 3.7 2.4 3.7 5"/>',
  plug: '<path d="M9 3v5M15 3v5"/><path d="M6.5 8h11v3.5a5.5 5.5 0 0 1-11 0z"/><path d="M12 17v4"/>',
  plus: '<path d="M12 5v14M5 12h14"/>',
  gear: '<circle cx="12" cy="12" r="3.2"/><path d="M19.4 15a1.7 1.7 0 0 0 .34 1.87l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.7 1.7 0 0 0-2.87 1.2V21a2 2 0 1 1-4 0v-.09A1.7 1.7 0 0 0 7.1 19.4l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06A1.7 1.7 0 0 0 3 13.7H3a2 2 0 1 1 0-4h.09A1.7 1.7 0 0 0 4.6 7.1L4.54 7a2 2 0 1 1 2.83-2.83l.06.06A1.7 1.7 0 0 0 10 4.6V3a2 2 0 1 1 4 0v.09a1.7 1.7 0 0 0 2.87 1.2l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06A1.7 1.7 0 0 0 21 10.3H21a2 2 0 1 1 0 4h-.09a1.7 1.7 0 0 0-1.51 1.02z"/>',
  sun: '<circle cx="12" cy="12" r="4.2"/><path d="M12 2.5v2.2M12 19.3v2.2M2.5 12h2.2M19.3 12h2.2M5.2 5.2l1.6 1.6M17.2 17.2l1.6 1.6M18.8 5.2l-1.6 1.6M6.8 17.2l-1.6 1.6"/>',
  moon: '<path d="M20.5 14.5A8.5 8.5 0 0 1 9.5 3.5a8.5 8.5 0 1 0 11 11z"/>',
  sync: '<path d="M20 11a8 8 0 0 0-14-4.5L4 9"/><path d="M4 5v4h4"/><path d="M4 13a8 8 0 0 0 14 4.5L20 15"/><path d="M20 19v-4h-4"/>',
  upload:
    '<path d="M12 16V4"/><path d="M7.5 8.5L12 4l4.5 4.5"/><path d="M4 16v2.5A1.5 1.5 0 0 0 5.5 20h13a1.5 1.5 0 0 0 1.5-1.5V16"/>',
  download:
    '<path d="M12 4v12"/><path d="M7.5 11.5L12 16l4.5-4.5"/><path d="M4 16v2.5A1.5 1.5 0 0 0 5.5 20h13a1.5 1.5 0 0 0 1.5-1.5V16"/>',
  key: '<circle cx="8" cy="15" r="4"/><path d="M11 12l8-8M17 4h3v3"/>',
  code: '<path d="M8.5 6L3 12l5.5 6M15.5 6L21 12l-5.5 6"/>',
  check: '<path d="M20 6L9 17l-5-5"/>',
  alert: '<path d="M12 8v5M12 16.5v.5"/><circle cx="12" cy="12" r="9"/>',
  doc: '<path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z"/><path d="M14 3v5h5"/>',
  link: '<path d="M10 13.5a4 4 0 0 0 5.7 0l2.6-2.6a4 4 0 0 0-5.7-5.7L11.4 6.5"/><path d="M14 10.5a4 4 0 0 0-5.7 0l-2.6 2.6a4 4 0 0 0 5.7 5.7l1.2-1.2"/>',
  // Feather `external-link`. Distinct from `link`, which is a chain and means
  // "these two things are related" — this one means "leaves the hub".
  externalLink:
    '<path d="M18 13.5v5A1.5 1.5 0 0 1 16.5 20h-11A1.5 1.5 0 0 1 4 18.5v-11A1.5 1.5 0 0 1 5.5 6h5"/><path d="M14 4h6v6"/><path d="M10.5 13.5L20 4"/>',
  // Feather `check-square` — a test case, as distinct from a bare `check`.
  checkSquare:
    '<path d="M9 11.5l2.5 2.5L20 5.5"/><path d="M20 12v6.5A1.5 1.5 0 0 1 18.5 20h-13A1.5 1.5 0 0 1 4 18.5v-13A1.5 1.5 0 0 1 5.5 4H16"/>',
  bolt: '<path d="M13 2L4.5 13.5H11l-1 8.5L19.5 10H13z"/>',
  git: '<circle cx="6" cy="6" r="2.6"/><circle cx="6" cy="18" r="2.6"/><circle cx="17" cy="12" r="2.6"/><path d="M6 8.6v6.8M8.6 6h3.4a2.4 2.4 0 0 1 2.4 2.4v1.2"/>',
  azure: '<path d="M9.5 3L4 18.5h4L14.5 3z"/><path d="M13 8l7 12.5H7l4-2.5"/>',
  jira: '<path d="M12 2.5l9 9-4.5 4.5-9-9z"/><path d="M7.5 11.5L3 16l5.5 5.5 4.5-4.5"/>',
  cpu: '<rect x="7" y="7" width="10" height="10" rx="2"/><path d="M10 3v3M14 3v3M10 18v3M14 18v3M3 10h3M3 14h3M18 10h3M18 14h3"/>',
  globe:
    '<circle cx="12" cy="12" r="9"/><path d="M3.5 9.5h17M3.5 14.5h17"/><path d="M12 3c2.6 3 2.6 15 0 18-2.6-3-2.6-15 0-18z"/>',
  logout:
    '<path d="M15 4h3.5A1.5 1.5 0 0 1 20 5.5v13a1.5 1.5 0 0 1-1.5 1.5H15"/><path d="M11 8l-4 4 4 4M7 12h9"/>',

  /* Extras the screens need, same drawing conventions. */
  search: '<circle cx="11" cy="11" r="7"/><path d="M20 20l-3.6-3.6"/>',
  arrowRight: '<path d="M5 12h14M13 6l6 6-6 6"/>',
  arrowLeft: '<path d="M19 12H5M11 6l-6 6 6 6"/>',
  chevronLeft: '<path d="M15 5l-7 7 7 7"/>',
  chevronUp: '<path d="M18 15l-6-6-6 6"/>',
  filter: '<path d="M3 5h18l-7 8v6l-4-2v-4z"/>',
  chevronRight: '<path d="M9 5l7 7-7 7"/>',
  chevronDown: '<path d="M6 9l6 6 6-6"/>',
  chevronUpDown: '<path d="M8 9l4-4 4 4M8 15l4 4 4-4"/>',
  close: '<path d="M6 6l12 12M18 6L6 18"/>',
  trash:
    '<path d="M4 7h16"/><path d="M9 7V5.5A1.5 1.5 0 0 1 10.5 4h3A1.5 1.5 0 0 1 15 5.5V7"/><path d="M6 7l1 12.5A1.5 1.5 0 0 0 8.5 21h7a1.5 1.5 0 0 0 1.5-1.5L18 7"/>',
  lock: '<rect x="4.5" y="10" width="15" height="10.5" rx="2.4"/><path d="M8 10V7.5a4 4 0 0 1 8 0V10"/>',
  bell: '<path d="M6 9a6 6 0 0 1 12 0c0 4.2 1.5 5.6 1.5 5.6h-15S6 13.2 6 9z"/><path d="M10 18.5a2 2 0 0 0 4 0"/>',
  eye: '<path d="M2.5 12S6 5.5 12 5.5 21.5 12 21.5 12 18 18.5 12 18.5 2.5 12 2.5 12z"/><circle cx="12" cy="12" r="3.2"/>',
  eyeOff:
    '<path d="M9.9 5.8A9.6 9.6 0 0 1 12 5.5c6 0 9.5 6.5 9.5 6.5a17 17 0 0 1-3.4 4.2M6.4 7.7A17 17 0 0 0 2.5 12S6 18.5 12 18.5a9.4 9.4 0 0 0 3.6-.7"/><path d="M3 3l18 18"/>',
  mail: '<rect x="3" y="5" width="18" height="14" rx="2.4"/><path d="M3.5 7l8.5 6 8.5-6"/>',
  copy: '<rect x="9" y="9" width="11" height="11" rx="2.2"/><path d="M5 15H4.5A1.5 1.5 0 0 1 3 13.5v-9A1.5 1.5 0 0 1 4.5 3h9A1.5 1.5 0 0 1 15 4.5V5"/>',
  more: '<circle cx="12" cy="5" r="1.4"/><circle cx="12" cy="12" r="1.4"/><circle cx="12" cy="19" r="1.4"/>',
  refresh: '<path d="M20 11a8 8 0 0 0-14-4.5L4 9"/><path d="M4 5v4h4"/>',
  layers:
    '<path d="M12 3l9 5-9 5-9-5z"/><path d="M3 13l9 5 9-5"/><path d="M3 17.5l9 5 9-5"/>',
} as const;

export type IconName = keyof typeof ICON_PATHS;

export interface IconProps extends Omit<SVGProps<SVGSVGElement>, "name"> {
  name: IconName;
  /** Rendered size in px. 12–22 per the handoff. Default 16. */
  size?: number;
  /** 2–2.6 per the handoff. Default 2. */
  strokeWidth?: number;
}

/** Inline SVG icon. Colour comes from `currentColor` — never a hex. */
export function Icon({
  name,
  size = 16,
  strokeWidth = 2,
  ...rest
}: IconProps) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={strokeWidth}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
      dangerouslySetInnerHTML={{ __html: ICON_PATHS[name] }}
      {...rest}
    />
  );
}

/**
 * The Claude mark — a FILLED 5-point star, not a stroked icon. Always rendered
 * in Claude terracotta (`--claude`); pass a class to override the size only.
 */
export function ClaudeMark({
  size = 16,
  className,
}: {
  size?: number;
  className?: string;
}) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="currentColor"
      className={className}
      aria-hidden="true"
      focusable="false"
    >
      <path d="M12 2l3.1 6.3 6.9 1-5 4.9 1.2 6.8L12 17.8 5.8 21l1.2-6.8-5-4.9 6.9-1z" />
    </svg>
  );
}

/** Spinner speed, per Handoff › Motion › `spin`. */
export type SpinnerSpeed = "upload" | "run" | "index";

const SPIN_CLASS: Record<SpinnerSpeed, string> = {
  upload: "animate-spin-upload",
  run: "animate-spin-run",
  index: "animate-spin-index",
};

/** A spinning arc. Durations: .7s upload, .8s test/import, .9s indexing. */
export function Spinner({
  size = 14,
  speed = "run",
  className,
}: {
  size?: number;
  speed?: SpinnerSpeed;
  className?: string;
}) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={2.4}
      strokeLinecap="round"
      className={cn(SPIN_CLASS[speed], className)}
      aria-hidden="true"
      focusable="false"
    >
      <path d="M12 3a9 9 0 1 0 9 9" />
    </svg>
  );
}
