// Handoff › 10. Settings › Appearance ("Ambient bloom range 0–100 step 5 with
// a mono % readout") and 6. Claude Settings › Models ("Parallel agent runs
// range 1–8").
//
// The filled portion of the track is the one legitimate inline style here: its
// width is a computed value, which the no-inline-styles rule exempts.

import { cn } from "@/lib/cn";

export interface RangeProps {
  value: number;
  onChange: (value: number) => void;
  min?: number;
  max?: number;
  step?: number;
  /** Small tracked uppercase label above the track. */
  label?: string;
  /** Mono readout on the right, e.g. "85%" or "2". */
  readout?: string;
  className?: string;
  "aria-label"?: string;
}

export function Range({
  value,
  onChange,
  min = 0,
  max = 100,
  step = 1,
  label,
  readout,
  className,
  "aria-label": ariaLabel,
}: RangeProps) {
  const pct = max === min ? 0 : ((value - min) / (max - min)) * 100;

  return (
    <div className={cn("flex flex-col gap-2", className)}>
      {(label || readout) && (
        <div className="flex items-center justify-between">
          {label && (
            <span className="text-[9.5px] font-bold tracking-[.11em] text-label">
              {label}
            </span>
          )}
          {readout && (
            <span className="font-mono text-[11.5px] font-semibold text-txt3">
              {readout}
            </span>
          )}
        </div>
      )}
      <div className="relative flex h-5 items-center">
        <span className="absolute inset-x-0 h-[6px] rounded-pill bg-inset" />
        <span
          className="absolute left-0 h-[6px] rounded-pill bg-accent-grad"
          style={{ width: `${pct}%` }}
        />
        <input
          type="range"
          min={min}
          max={max}
          step={step}
          value={value}
          aria-label={ariaLabel ?? label}
          onChange={(e) => onChange(Number(e.target.value))}
          className={cn(
            "relative z-10 h-5 w-full cursor-pointer appearance-none bg-transparent",
            "[&::-webkit-slider-thumb]:size-[16px] [&::-webkit-slider-thumb]:appearance-none",
            "[&::-webkit-slider-thumb]:rounded-full [&::-webkit-slider-thumb]:bg-p",
            "[&::-webkit-slider-thumb]:shadow-primary",
            "[&::-moz-range-thumb]:size-[16px] [&::-moz-range-thumb]:rounded-full",
            "[&::-moz-range-thumb]:border-0 [&::-moz-range-thumb]:bg-p",
          )}
        />
      </div>
    </div>
  );
}
