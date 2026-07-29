// Handoff › Design Tokens › "Semantic status colours".
//
// Takes a semantic status string and resolves colour + tint from the token
// layer — which already carries the light-mode darkening map, so this component
// needs no mode awareness and contains no hex.

import { Pill, type PillProps, type PillTone } from "./Pill";

/** Every status string the screens render, mapped to its semantic tone. */
export const STATUS_TONE = {
  // #6ee7b7 on rgba(16,185,129,.13–.14)
  Done: "ok",
  Passed: "ok",
  Imported: "ok",
  Indexed: "ok",
  Connected: "ok",
  Active: "ok",
  Verified: "ok",
  Live: "ok",
  // #fbbf24 on rgba(251,191,36,.13–.14)
  "In progress": "warn",
  Importing: "warn",
  Pending: "warn",
  Attention: "warn",
  Expiring: "warn",
  "Needs refresh": "warn",
  // #fb7185 on rgba(244,63,94,.14)
  Blocked: "danger",
  Failed: "danger",
  Expired: "danger",
  Disconnected: "danger",
  // #a5f3fc on rgba(34,211,238,.13)
  "In review": "info",
  // Issue #63 — an elapsed Claude access token that has a refresh token beside
  // it. Informational, not green: the token on file really has lapsed, the CLI
  // just renews it on the next run. Nothing is wrong and nothing is verified.
  Refreshes: "info",
  // #c3cad6 / #8b8b9e on rgba(255,255,255,.07)
  New: "neutral",
  Paused: "neutral",
  "Not indexed": "neutral",
  Unassigned: "neutral",
  Placeholder: "neutral",
} as const satisfies Record<string, PillTone>;

export type StatusName = keyof typeof STATUS_TONE;

export interface StatusPillProps extends Omit<PillProps, "tone" | "children"> {
  status: StatusName;
  /** Prefix the label with a pulsing status dot. */
  pulse?: boolean;
}

/** Resolve the tone for a status. Unknown statuses fall back to neutral. */
export function statusTone(status: string): PillTone {
  return (STATUS_TONE as Record<string, PillTone>)[status] ?? "neutral";
}

export function StatusPill({
  status,
  pulse = false,
  dot,
  className,
  ...rest
}: StatusPillProps) {
  return (
    <Pill
      tone={statusTone(status)}
      dot={dot ?? pulse}
      dotPulse={pulse}
      className={className}
      {...rest}
    >
      {status}
    </Pill>
  );
}
