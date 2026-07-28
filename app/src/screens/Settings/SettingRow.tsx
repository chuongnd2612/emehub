// Handoff § 10. Settings — the row shapes the three cards share:
// a label (13.5px/700) + description (12px, --muted) on the left, and a
// control on the right. `ToggleRow` adds the On/Off readout the prototype
// renders next to every switch.

import type { ReactNode } from "react";

import { Toggle } from "@/components/ui";
import { cn } from "@/lib/cn";

export interface SettingRowProps {
  label: string;
  description: string;
  /** Overrides the text column's wrap threshold (`min-w-*`). */
  textClassName?: string;
  className?: string;
  children?: ReactNode;
}

export function SettingRow({
  label,
  description,
  textClassName,
  className,
  children,
}: SettingRowProps) {
  return (
    <div className={cn("flex flex-wrap items-center gap-[14px]", className)}>
      <div className={cn("min-w-[200px] flex-1", textClassName)}>
        <div className="text-[13.5px] font-bold text-txt2">{label}</div>
        <div className="mt-[3px] text-[12px] leading-[1.5] text-muted">
          {description}
        </div>
      </div>
      {children}
    </div>
  );
}

export interface ToggleRowProps {
  label: string;
  description: string;
  checked: boolean;
  onChange: (checked: boolean) => void;
  className?: string;
}

export function ToggleRow({
  label,
  description,
  checked,
  onChange,
  className,
}: ToggleRowProps) {
  return (
    <SettingRow label={label} description={description} className={className}>
      <span className="w-7 text-right text-[11.5px] font-bold text-muted">
        {checked ? "On" : "Off"}
      </span>
      {/* The shared primitive already animates the knob with
          `left .22s cubic-bezier(.2,.7,.3,1)`. */}
      <Toggle checked={checked} onChange={onChange} aria-label={label} />
    </SettingRow>
  );
}

/** The 1px hairline the Appearance card uses between blocks. */
export function Hairline() {
  return <div className="h-px bg-bd3" />;
}

/** A chip in a Workspace-defaults chip group. */
export function OptionChip({
  label,
  active,
  onClick,
}: {
  label: string;
  active: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      aria-pressed={active}
      onClick={onClick}
      className={cn(
        "cursor-pointer rounded-control border px-[14px] py-[7px] text-[12px] font-bold",
        "transition-[background-color,border-color,color] duration-200",
        active
          ? "border-pb bg-pt text-p-on"
          : "border-bd bg-inset text-muted hover:bg-card3 hover:text-txt3",
      )}
    >
      {label}
    </button>
  );
}
