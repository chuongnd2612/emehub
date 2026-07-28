// Handoff › 5. Import dialog ("segmented Basic | Advanced in a 4px inset
// track") and 10. Settings › Appearance ("Interface mode segmented Dark|Light,
// active = var(--pg) + #fff + accent glow").

import type { ReactNode } from "react";
import { cn } from "@/lib/cn";

export interface SegmentedOption<T extends string> {
  value: T;
  label: string;
  icon?: ReactNode;
}

export interface SegmentedProps<T extends string> {
  options: SegmentedOption<T>[];
  value: T;
  onChange: (value: T) => void;
  /**
   * `tint` — active segment is `--pt` + `--pb` (the import dialog).
   * `solid` — active segment is the `--pg` gradient with the accent glow
   * (Settings › Interface mode).
   */
  variant?: "tint" | "solid";
  className?: string;
}

export function Segmented<T extends string>({
  options,
  value,
  onChange,
  variant = "tint",
  className,
}: SegmentedProps<T>) {
  return (
    <div
      data-surface
      role="tablist"
      className={cn(
        "inline-flex gap-1 rounded-button border border-bd2 bg-inset p-1",
        className,
      )}
    >
      {options.map((o) => {
        const active = o.value === value;
        return (
          <button
            key={o.value}
            type="button"
            role="tab"
            aria-selected={active}
            onClick={() => onChange(o.value)}
            className={cn(
              "inline-flex cursor-pointer items-center justify-center gap-2 rounded-control px-4 py-[7px]",
              "text-[12.5px] font-bold transition-[background-color,color,box-shadow] duration-200",
              !active && "text-txt4 hover:bg-card3 hover:text-txt2",
              active &&
                (variant === "solid"
                  ? "bg-accent-grad text-white shadow-primary"
                  : "border border-pb bg-pt text-p-on"),
            )}
          >
            {o.icon}
            {o.label}
          </button>
        );
      })}
    </div>
  );
}
