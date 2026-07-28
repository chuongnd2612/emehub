// Handoff › Spacing, radius, elevation › "Glass recipe":
//   background:var(--card); backdrop-filter:blur(22px); border:1px solid var(--bd)
// Panels use --panel + blur(28px) and the panel shadow.

import type { HTMLAttributes, ReactNode } from "react";
import { cn } from "@/lib/cn";

export interface GlassCardProps extends HTMLAttributes<HTMLDivElement> {
  /** `card` = the 22px-blur glass recipe; `panel` = sidebar/header glass. */
  variant?: "card" | "panel";
  /** Card 16–22, panel 20–22. */
  radius?: "card" | "panel";
  /** Adds `translateY(-3px)` + accent border on hover (Handoff › Motion). */
  hoverable?: boolean;
  children?: ReactNode;
}

export function GlassCard({
  variant = "card",
  radius,
  hoverable = false,
  className,
  children,
  ...rest
}: GlassCardProps) {
  const r = radius ?? (variant === "panel" ? "panel" : "card");
  return (
    <div
      data-surface
      className={cn(
        variant === "panel" ? "glass-panel shadow-panel" : "glass",
        r === "panel" ? "rounded-panel" : "rounded-card",
        hoverable &&
          "transition-[background-color,border-color,transform] duration-200 hover:-translate-y-[3px] hover:border-pb hover:bg-card3",
        className,
      )}
      {...rest}
    >
      {children}
    </div>
  );
}
