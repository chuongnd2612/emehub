// Loading placeholders that match the shape of what is coming.
//
// Why not the spinner: a spinner is right for an indeterminate wait with no known
// shape (a modal action, a list whose length nobody knows yet). The Overview's
// tiles, feed rows and cards all have a FIXED geometry, so the honest loading
// state is that geometry — the layout lands immediately and then fills in, rather
// than the page sitting blank and then jumping.
//
// `LoadingState` is deliberately kept for the indeterminate cases.
//
// The shimmer is `.skeleton` in styles/theme.css. It sweeps a percentage of each
// block's own width, so a wide tile and a narrow chip travel in lockstep and the
// group reads as one surface being revealed instead of a dozen things flashing
// out of step.

import type { CSSProperties, ReactNode } from "react";
import { cn } from "@/lib/cn";
import { GlassCard } from "./GlassCard";

export interface SkeletonProps {
  className?: string;
  /** Rounded to match the thing it stands in for. */
  radius?: "sm" | "md" | "pill" | "glyph";
  /**
   * Computed dimensions only — a staggered row width, a first-column cap. The
   * handoff allows an inline style exactly where the value is genuinely
   * computed, and these are (they vary per index).
   */
  style?: CSSProperties;
}

const RADIUS: Record<NonNullable<SkeletonProps["radius"]>, string> = {
  sm: "rounded-[6px]",
  md: "rounded-[10px]",
  pill: "rounded-full",
  glyph: "rounded-glyph",
};

/** One placeholder block. Size it with `className`. */
export function Skeleton({ className, radius = "sm", style }: SkeletonProps) {
  return (
    <span className={cn("skeleton block", RADIUS[radius], className)} style={style} />
  );
}

/**
 * Wrapper announcing a region as loading.
 *
 * `aria-busy` plus `role="status"` matters here: without it a screen reader meets
 * a pile of empty decorative boxes and reports the region as empty, which is the
 * accessibility version of the bug this replaces.
 */
export function SkeletonRegion({
  label = "Loading…",
  className,
  children,
}: {
  label?: string;
  className?: string;
  children: ReactNode;
}) {
  return (
    <div role="status" aria-busy="true" aria-label={label} className={className}>
      {children}
    </div>
  );
}

/* ── Composed shapes, matching the real components ───────────────────────── */

/** Stands in for `KpiTiles`. Four is the usual count for an admin. */
export function KpiTilesSkeleton({ tiles = 4 }: { tiles?: number }) {
  return (
    <SkeletonRegion label="Loading workspace figures" className="grid grid-cols-4 gap-[14px]">
      {Array.from({ length: tiles }, (_, i) => (
        <GlassCard key={i} className="flex flex-col gap-3 p-[18px]">
          <Skeleton className="h-[9px] w-[64px]" />
          <div className="flex items-end gap-[10px]">
            <Skeleton className="h-[30px] w-[58px]" radius="md" />
            <Skeleton className="mb-1 h-[10px] w-[52px]" />
          </div>
        </GlassCard>
      ))}
    </SkeletonRegion>
  );
}

/** Stands in for one `ActivityFeed` row: glyph, two lines, a timestamp. */
export function ActivityRowsSkeleton({ rows = 6 }: { rows?: number }) {
  return (
    <SkeletonRegion label="Loading recent activity" className="flex flex-col">
      {Array.from({ length: rows }, (_, i) => (
        <div
          key={i}
          className="flex items-start gap-3 border-b border-bd3 py-[13px] last:border-b-0"
        >
          <Skeleton className="size-7 shrink-0" radius="glyph" />
          <div className="flex min-w-0 flex-1 flex-col gap-2">
            {/* Staggered widths — rows of identical length look like a table,
                not like prose that is about to arrive. */}
            <Skeleton
              className="h-[11px]"
              // A computed width is the one legitimate inline style (handoff rule).
              style={{ width: `${58 + ((i * 13) % 34)}%` }}
            />
            <Skeleton className="h-[9px] w-[38%]" />
          </div>
          <Skeleton className="mt-[2px] h-[9px] w-[44px] shrink-0" />
        </div>
      ))}
    </SkeletonRegion>
  );
}

/** Stands in for a `ProductCard` pair. */
export function ProductCardsSkeleton() {
  return (
    <SkeletonRegion label="Loading agents" className="grid grid-cols-2 gap-[14px]">
      {[0, 1].map((i) => (
        <GlassCard key={i} radius="panel" className="flex flex-col gap-4 p-5">
          <div className="flex items-center gap-3">
            <Skeleton className="size-[34px] shrink-0" radius="glyph" />
            <div className="flex flex-1 flex-col gap-2">
              <Skeleton className="h-[13px] w-[92px]" />
              <Skeleton className="h-[9px] w-[120px]" />
            </div>
            <Skeleton className="h-[30px] w-[86px] shrink-0" radius="md" />
          </div>
          <Skeleton className="h-[9px] w-full" />
          <Skeleton className="h-[9px] w-[84%]" />
          <div className="flex gap-2">
            <Skeleton className="h-[20px] w-[86px]" radius="pill" />
            <Skeleton className="h-[20px] w-[70px]" radius="pill" />
            <Skeleton className="h-[20px] w-[96px]" radius="pill" />
          </div>
        </GlassCard>
      ))}
    </SkeletonRegion>
  );
}

/** Stands in for a panel's title row, so the heading does not pop in alone. */
export function PanelHeadingSkeleton() {
  return (
    <div className="mb-[6px] flex items-center gap-[10px]">
      <Skeleton className="h-[13px] w-[118px]" />
      <Skeleton className="ml-auto h-[9px] w-[54px]" />
    </div>
  );
}

/** Stands in for a right-hand summary panel (integrations / projects). */
export function SummaryPanelSkeleton({ rows = 2 }: { rows?: number }) {
  return (
    <SkeletonRegion label="Loading" className="flex flex-col gap-3">
      {Array.from({ length: rows }, (_, i) => (
        <div key={i} className="flex items-center gap-3 rounded-card bg-card3 p-3.5">
          <Skeleton className="size-8 shrink-0" radius="glyph" />
          <div className="flex min-w-0 flex-1 flex-col gap-2">
            <Skeleton className="h-[11px] w-[45%]" />
            <Skeleton className="h-[9px] w-[68%]" />
          </div>
        </div>
      ))}
    </SkeletonRegion>
  );
}

/** Stands in for table rows — tickets, members, anything on the shared Table. */
export function TableRowsSkeleton({
  rows = 8,
  columns = 6,
}: {
  rows?: number;
  columns?: number;
}) {
  return (
    <SkeletonRegion label="Loading rows" className="flex flex-col">
      {Array.from({ length: rows }, (_, r) => (
        <div
          key={r}
          className="flex items-center gap-4 border-b border-bd3 px-[18px] py-[15px] last:border-b-0"
        >
          {Array.from({ length: columns }, (_, c) => (
            <Skeleton
              key={c}
              className="h-[11px] flex-1"
              style={{ maxWidth: c === 0 ? 74 : undefined }}
            />
          ))}
        </div>
      ))}
    </SkeletonRegion>
  );
}
