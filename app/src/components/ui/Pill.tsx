// Handoff › Design Tokens › radius "pill 20". The generic tinted chip used for
// tags, agent pills, badges and small tracked labels. StatusPill wraps this for
// the semantic statuses.

import type { HTMLAttributes, ReactNode } from "react";
import { cn } from "@/lib/cn";

export type PillTone =
  | "neutral"
  | "accent"
  | "qagent"
  | "dagent"
  | "claude"
  | "ok"
  | "warn"
  | "danger"
  | "info";

export interface PillProps extends HTMLAttributes<HTMLSpanElement> {
  tone?: PillTone;
  /** `sm` = 10px meta chip, `md` = 11px tag pill. */
  size?: "sm" | "md";
  /** Renders the label in JetBrains Mono (IDs, versions, counts). */
  mono?: boolean;
  /** A 7px leading dot in the tone's colour. */
  dot?: boolean;
  /** Animate the leading dot with `pulseDot` (all live status dots). */
  dotPulse?: boolean;
  children?: ReactNode;
}

const TONE: Record<PillTone, string> = {
  neutral: "bg-card3 border-bd text-txt4",
  accent: "bg-pt border-pb text-p-on",
  qagent: "bg-qagent-tint border-transparent text-qagent",
  dagent: "bg-dagent-tint border-transparent text-dagent",
  claude: "bg-claude-tint border-transparent text-terra",
  ok: "bg-ok-tint border-transparent text-ok",
  warn: "bg-warn-tint border-transparent text-warn",
  danger: "bg-danger-tint border-transparent text-danger",
  info: "bg-info-tint border-transparent text-info",
};

const DOT: Record<PillTone, string> = {
  neutral: "bg-muted",
  accent: "bg-p",
  qagent: "bg-qagent",
  dagent: "bg-dagent",
  claude: "bg-claude",
  ok: "bg-ok",
  warn: "bg-warn",
  danger: "bg-danger",
  info: "bg-info",
};

export function Pill({
  tone = "neutral",
  size = "md",
  mono = false,
  dot = false,
  dotPulse = false,
  className,
  children,
  ...rest
}: PillProps) {
  return (
    <span
      data-surface
      className={cn(
        "inline-flex items-center gap-1.5 rounded-pill border font-semibold whitespace-nowrap",
        size === "sm" ? "px-[7px] py-[2px] text-[10px]" : "px-[11px] py-[5px] text-[11px]",
        mono && "font-mono font-bold",
        TONE[tone],
        className,
      )}
      {...rest}
    >
      {dot && (
        <span
          className={cn(
            "size-[7px] shrink-0 rounded-full",
            DOT[tone],
            dotPulse && "animate-pulse-dot",
          )}
        />
      )}
      {children}
    </span>
  );
}
