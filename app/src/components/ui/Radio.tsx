// Handoff › 5. Import dialog › Basic — "three radio rows (18px ring, filled
// 8px dot when on). Selected row: var(--pt) + var(--pb)."

import type { ReactNode } from "react";
import { cn } from "@/lib/cn";

export interface RadioProps {
  checked: boolean;
  onChange: () => void;
  label: ReactNode;
  /** Right-aligned hint, e.g. "~24 items". */
  hint?: ReactNode;
  name?: string;
  disabled?: boolean;
  className?: string;
}

/** One full-width selectable row with an 18px ring. */
export function Radio({
  checked,
  onChange,
  label,
  hint,
  name,
  disabled = false,
  className,
}: RadioProps) {
  return (
    <label
      data-surface
      className={cn(
        "flex cursor-pointer items-center gap-3 rounded-control-lg border px-3.5 py-3",
        "transition-[background-color,border-color] duration-200",
        checked
          ? "border-pb bg-pt"
          : "border-bd2 bg-card2 hover:bg-card3",
        disabled && "cursor-not-allowed opacity-50",
        className,
      )}
    >
      <input
        type="radio"
        name={name}
        checked={checked}
        disabled={disabled}
        onChange={onChange}
        className="sr-only"
      />
      <span
        className={cn(
          "flex size-[18px] shrink-0 items-center justify-center rounded-full border-2",
          checked ? "border-p" : "border-bd2",
        )}
      >
        {checked && <span className="size-[8px] rounded-full bg-p" />}
      </span>
      <span className="flex-1 text-[13px] font-semibold text-txt2">{label}</span>
      {hint && <span className="text-[11.5px] text-faint">{hint}</span>}
    </label>
  );
}

export interface RadioGroupProps<T extends string> {
  name: string;
  value: T;
  onChange: (value: T) => void;
  options: { value: T; label: ReactNode; hint?: ReactNode }[];
  className?: string;
}

export function RadioGroup<T extends string>({
  name,
  value,
  onChange,
  options,
  className,
}: RadioGroupProps<T>) {
  return (
    <div role="radiogroup" className={cn("flex flex-col gap-2", className)}>
      {options.map((o) => (
        <Radio
          key={o.value}
          name={name}
          checked={o.value === value}
          onChange={() => onChange(o.value)}
          label={o.label}
          hint={o.hint}
        />
      ))}
    </div>
  );
}
