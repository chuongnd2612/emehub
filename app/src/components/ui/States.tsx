// Loading, error and inline-notice states — the three things every screen that
// does real I/O needs and the handoff never draws.
//
// Derived from what the handoff DOES specify:
//   • `EmptyState` is the shipped empty-state recipe verbatim (Voice: "a glyph,
//     a one-line explanation and a primary CTA — never a bare 'no data'"), the
//     same one `TableEmpty` renders inside a table.
//   • `ErrorState` is that recipe in the rose destructive treatment, because a
//     failed request must say what failed. It always offers Retry.
//   • `Notice` is the handoff's inline warning strip (Create API key modal:
//     amber tint + hairline + 15px alert glyph), generalised to the three
//     semantic tones.
//   • `LoadingState` uses the spec'd spinner (`spin .8s`) with a
//     present-participle line, matching the async-feedback table's voice.

import type { ReactNode } from "react";

import { cn } from "@/lib/cn";
import { Icon, Spinner, type IconName } from "./Icon";

/* ── Loading ─────────────────────────────────────────────────────────────── */

export interface LoadingStateProps {
  /** Present participle, e.g. "Loading sessions…". */
  label: string;
  /** Tighter padding for use inside a card rather than a full panel. */
  compact?: boolean;
  className?: string;
}

export function LoadingState({ label, compact, className }: LoadingStateProps) {
  return (
    <div
      role="status"
      aria-live="polite"
      className={cn(
        "flex items-center justify-center gap-2.5 text-[12.5px] font-semibold text-muted",
        compact ? "py-8" : "py-16",
        className,
      )}
    >
      <Spinner size={16} speed="run" className="text-pl" />
      {label}
    </div>
  );
}

/* ── Empty ───────────────────────────────────────────────────────────────── */

export interface EmptyStateProps {
  icon?: IconName;
  /** One line, sentence case. Never "No data". */
  title: string;
  /** Optional second line explaining what to do next. */
  body?: string;
  /** Primary CTA. */
  action?: ReactNode;
  className?: string;
}

export function EmptyState({
  icon = "search",
  title,
  body,
  action,
  className,
}: EmptyStateProps) {
  return (
    <div
      className={cn(
        "flex flex-col items-center gap-[9px] px-5 py-[46px] text-center",
        className,
      )}
    >
      <span className="flex size-10 items-center justify-center rounded-[13px] border border-bd2 bg-card3 text-label">
        <Icon name={icon} size={19} strokeWidth={2.2} />
      </span>
      <p className="m-0 text-[13.5px] font-bold text-txt2">{title}</p>
      {body && (
        <p className="m-0 max-w-[42ch] text-[12.5px] leading-[1.55] text-pretty text-muted">
          {body}
        </p>
      )}
      {action && <div className="mt-1">{action}</div>}
    </div>
  );
}

/* ── Error ───────────────────────────────────────────────────────────────── */

export interface ErrorStateProps {
  /** What failed, e.g. "Could not load your sessions". */
  title: string;
  /** The reason — normally `ApiError.message`. Never swallow this. */
  detail?: string;
  /** Rendered as the primary CTA when given. */
  onRetry?: () => void;
  retryLabel?: string;
  className?: string;
}

export function ErrorState({
  title,
  detail,
  onRetry,
  retryLabel = "Try again",
  className,
}: ErrorStateProps) {
  return (
    <div
      role="alert"
      className={cn(
        "flex flex-col items-center gap-[9px] px-5 py-[46px] text-center",
        className,
      )}
    >
      <span className="flex size-10 items-center justify-center rounded-[13px] border border-danger/30 bg-danger-tint text-danger">
        <Icon name="alert" size={19} strokeWidth={2.2} />
      </span>
      <p className="m-0 text-[13.5px] font-bold text-txt2">{title}</p>
      {detail && (
        <p className="m-0 max-w-[46ch] text-[12.5px] leading-[1.55] text-pretty text-muted">
          {detail}
        </p>
      )}
      {onRetry && (
        <button
          type="button"
          data-surface
          onClick={onRetry}
          className={cn(
            "mt-1 inline-flex cursor-pointer items-center gap-[7px] rounded-control",
            "border border-bd2 bg-card2 px-[15px] py-[9px] text-[12.5px] font-semibold text-txt3",
            "hover:bg-bd3 hover:text-txt2",
          )}
        >
          <Icon name="refresh" size={13} strokeWidth={2.4} />
          {retryLabel}
        </button>
      )}
    </div>
  );
}

/* ── Inline notice ───────────────────────────────────────────────────────── */

export type NoticeTone = "warn" | "danger" | "info";

/** Tone → surface classes + glyph. Tokens only; no hex. */
const NOTICE_TONE: Record<NoticeTone, { box: string; icon: IconName }> = {
  warn: { box: "border-warn/25 bg-warn-tint text-warn", icon: "alert" },
  danger: { box: "border-danger/30 bg-danger-tint text-danger", icon: "alert" },
  info: { box: "border-pb bg-pt text-ps-text", icon: "bolt" },
};

export interface NoticeProps {
  tone?: NoticeTone;
  children: ReactNode;
  className?: string;
}

/**
 * The handoff's inline warning strip. Use it for a failure that belongs beside
 * the control that caused it (a rejected login, an invalid code) and for the
 * "this is preview data" labels on the panels that still run on fixtures.
 */
export function Notice({ tone = "warn", children, className }: NoticeProps) {
  const t = NOTICE_TONE[tone];
  return (
    <div
      role={tone === "danger" ? "alert" : "status"}
      className={cn(
        "flex items-start gap-2.5 rounded-[13px] border px-[15px] py-[13px]",
        "text-[12px] leading-[1.5]",
        t.box,
        className,
      )}
    >
      <Icon
        name={t.icon}
        size={15}
        strokeWidth={2.2}
        className="mt-px shrink-0"
      />
      <span className="min-w-0 flex-1">{children}</span>
    </div>
  );
}
