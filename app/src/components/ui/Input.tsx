// Handoff › 9. Integrations ("text/password inputs, focus border var(--pb)")
// and Motion — transitions ("border-color .2s on inputs/cards").

import { useId, type InputHTMLAttributes, type ReactNode } from "react";
import { cn } from "@/lib/cn";

export interface InputProps extends InputHTMLAttributes<HTMLInputElement> {
  /** Small tracked uppercase label above the field. */
  label?: string;
  /** Renders the value in JetBrains Mono (JQL, search queries, IDs, paths). */
  mono?: boolean;
  /** Leading adornment, typically an `<Icon />`. */
  icon?: ReactNode;
  /** Trailing adornment, e.g. a `⌘K` chip or a Reveal button. */
  trailing?: ReactNode;
}

export function Input({
  label,
  mono = false,
  icon,
  trailing,
  className,
  id,
  ...rest
}: InputProps) {
  const autoId = useId();
  const inputId = id ?? autoId;

  const field = (
    <div
      data-surface
      className={cn(
        "flex h-9 items-center gap-2 rounded-control-lg border border-bd2 bg-card2 px-3",
        "transition-colors duration-200 focus-within:border-pb",
        className,
      )}
    >
      {icon && <span className="flex shrink-0 text-faint">{icon}</span>}
      <input
        id={inputId}
        className={cn(
          "min-w-0 flex-1 bg-transparent text-[12.5px] font-semibold text-txt2 outline-none",
          "placeholder:font-medium placeholder:text-faint",
          mono && "font-mono text-[12px]",
        )}
        {...rest}
      />
      {trailing && <span className="flex shrink-0">{trailing}</span>}
    </div>
  );

  if (!label) return field;

  return (
    // `min-w-0` because this wrapper — not the field box `className` targets —
    // is the flex/grid item of whatever row the caller puts it in. Without it a
    // long value pushes past the track's share and the columns go uneven (#188).
    <label htmlFor={inputId} className="flex min-w-0 flex-col gap-[7px]">
      <span className="text-[9.5px] font-bold tracking-[.11em] text-label">
        {label}
      </span>
      {field}
    </label>
  );
}
