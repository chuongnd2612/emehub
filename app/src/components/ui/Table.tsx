// Handoff › 4. Tickets and 8. User Management — the tables are CSS grids with
// explicit column templates (e.g. `110px | 2.4fr | 1fr | 120px | …`, gap 12),
// a 9.5px/700/.11em header row, 14px/20px row padding, a 1px var(--bd3)
// divider and a var(--card3) row hover.
//
// The `columns` template is data (it differs per table), so it lands on the
// element as a computed grid-template-columns — the inline-style exemption.

import type { HTMLAttributes, ReactNode } from "react";
import { cn } from "@/lib/cn";
import { GlassCard } from "./GlassCard";
import { Icon, type IconName } from "./Icon";

export interface TableProps extends HTMLAttributes<HTMLDivElement> {
  children?: ReactNode;
}

/** Glass container. Below ~1100px it scrolls horizontally, per the handoff. */
export function Table({ className, children, ...rest }: TableProps) {
  return (
    <GlassCard className={cn("overflow-x-auto", className)} {...rest}>
      <div className="min-w-[1100px]">{children}</div>
    </GlassCard>
  );
}

export interface TableRowProps extends HTMLAttributes<HTMLDivElement> {
  /** CSS grid template, e.g. `110px 2.4fr 1fr 120px 120px 110px 110px`. */
  columns: string;
  /** Uppercase tracked header row — no hover, no divider above. */
  header?: boolean;
  /** Row responds to hover + click. */
  interactive?: boolean;
  children?: ReactNode;
}

export function TableRow({
  columns,
  header = false,
  interactive = false,
  className,
  children,
  ...rest
}: TableRowProps) {
  return (
    <div
      role="row"
      style={{ gridTemplateColumns: columns }}
      className={cn(
        "grid items-center gap-3 px-5",
        header
          ? "border-b border-bd3 py-3 text-[9.5px] font-bold tracking-[.11em] text-label"
          : "border-b border-bd3 py-3.5 text-[12.5px] text-txt3 last:border-b-0",
        interactive &&
          "cursor-pointer transition-colors duration-200 hover:bg-card3",
        className,
      )}
      {...rest}
    >
      {children}
    </div>
  );
}

export interface TableCellProps extends HTMLAttributes<HTMLDivElement> {
  /** Render in JetBrains Mono (IDs, paths, timestamps, counts). */
  mono?: boolean;
  align?: "start" | "center" | "end";
  children?: ReactNode;
}

export function TableCell({
  mono = false,
  align = "start",
  className,
  children,
  ...rest
}: TableCellProps) {
  return (
    <div
      role="cell"
      className={cn(
        "flex min-w-0 items-center gap-2 truncate",
        align === "end" && "justify-end",
        align === "center" && "justify-center",
        mono && "font-mono text-[11.5px] font-bold",
        className,
      )}
      {...rest}
    >
      {children}
    </div>
  );
}

export interface TableEmptyProps {
  /** Glyph for the empty state — never a bare "no data" (Handoff › Voice). */
  icon?: IconName;
  /** One-line explanation, e.g. "No work items match these filters". */
  message: string;
  /** Primary CTA. */
  action?: ReactNode;
}

export function TableEmpty({
  icon = "search",
  message,
  action,
}: TableEmptyProps) {
  return (
    <div className="flex flex-col items-center gap-3 px-5 py-16 text-center">
      <span className="flex size-[42px] items-center justify-center rounded-glyph border border-bd2 bg-bd3 text-txt4">
        <Icon name={icon} size={19} strokeWidth={2.2} />
      </span>
      <p className="m-0 text-[13px] font-semibold text-muted">{message}</p>
      {action}
    </div>
  );
}

/** Small print under a table, e.g. the tickets read-only-mirror footnote. */
export function TableFootnote({
  icon = "lock",
  children,
}: {
  icon?: IconName;
  children: ReactNode;
}) {
  return (
    <div className="flex items-center gap-2 px-1 text-[11.5px] text-faint">
      <Icon name={icon} size={12} strokeWidth={2.2} />
      <span>{children}</span>
    </div>
  );
}
