// Handoff › Motion — transitions: the knob carries
// `left .22s cubic-bezier(.2,.7,.3,1)`.
//
// The prototype DROPPED that transition (preview-runtime limitation, called out
// in the handoff's "Prototype caveat"). It is restored here — this is one of
// the two transitions CLAUDE.md explicitly requires back.

import type { ReactNode } from "react";
import { cn } from "@/lib/cn";

export interface ToggleProps {
  checked: boolean;
  onChange: (checked: boolean) => void;
  /** Row label. Omit for a bare switch. */
  label?: ReactNode;
  /** Secondary line under the label. */
  description?: ReactNode;
  disabled?: boolean;
  className?: string;
  "aria-label"?: string;
}

export function Toggle({
  checked,
  onChange,
  label,
  description,
  disabled = false,
  className,
  "aria-label": ariaLabel,
}: ToggleProps) {
  const knob = (
    <span
      role="switch"
      aria-checked={checked}
      aria-label={ariaLabel ?? (typeof label === "string" ? label : undefined)}
      tabIndex={disabled ? -1 : 0}
      onClick={() => !disabled && onChange(!checked)}
      onKeyDown={(e) => {
        if (disabled) return;
        if (e.key === " " || e.key === "Enter") {
          e.preventDefault();
          onChange(!checked);
        }
      }}
      data-surface
      className={cn(
        "relative block h-[22px] w-[40px] shrink-0 cursor-pointer rounded-pill border",
        "transition-colors duration-200 outline-none focus-visible:border-pb",
        checked ? "border-pb bg-pt" : "border-bd2 bg-inset",
        disabled && "cursor-not-allowed opacity-50",
      )}
    >
      <span
        className={cn(
          // `left` is animated, not `transform` — matching the handoff exactly.
          "absolute top-[2px] size-[16px] rounded-full",
          "transition-[left,background-color] duration-[.22s] ease-[cubic-bezier(.2,.7,.3,1)]",
          checked ? "left-[20px] bg-p" : "left-[2px] bg-muted",
        )}
      />
    </span>
  );

  if (!label && !description) return <span className={className}>{knob}</span>;

  return (
    <div className={cn("flex items-center gap-3", className)}>
      <div className="min-w-0 flex-1">
        {label && (
          <div className="text-[13px] font-bold text-txt2">{label}</div>
        )}
        {description && (
          <div className="mt-[3px] text-[11.5px] leading-[1.5] text-faint">
            {description}
          </div>
        )}
      </div>
      {knob}
    </div>
  );
}
