// NO DESIGN WAS SUPPLIED FOR THE UNAUTHENTICATED SCREENS.
//
// Derived from QAgent's `app/src/components/auth/fields.tsx` (label above a
// 46px pill field, leading icon slot, password reveal toggle, a centred
// wide-tracked one-time-code input) and restyled onto EmeHub's tokens.
//
// Why not the shared `components/ui/Input`? That primitive is the 36px table /
// toolbar field and other screens depend on its metrics. The handoff's *form*
// input is a different size — "padding:12px 14px; border-radius:11px;
// background:var(--card3); border:1px solid var(--bd2); font-size:13.5px",
// focus border var(--pb) — so these render that recipe instead of stretching a
// primitive two slices are about to build on.
//
// Field labels are the handoff's tracked label: 9.5px / 700 / .11em /
// var(--label), above the field, never a placeholder-as-label.

import {
  useId,
  useState,
  type InputHTMLAttributes,
  type ReactNode,
} from "react";

import { Icon } from "@/components/ui";
import { cn } from "@/lib/cn";

/* ── Headings ────────────────────────────────────────────────────────────── */

/** Title + subtitle above an auth form. Modal typography: 19px/900/-.03em. */
export function AuthHeading({
  title,
  subtitle,
}: {
  title: string;
  subtitle?: ReactNode;
}) {
  return (
    <div className="mb-[22px]">
      <h1 className="m-0 text-[23px] leading-tight font-black tracking-[-.035em] text-txt">
        {title}
      </h1>
      {subtitle && (
        <p className="m-0 mt-[7px] text-[12.5px] leading-[1.55] text-pretty text-muted">
          {subtitle}
        </p>
      )}
    </div>
  );
}

/** "Back to sign in"-style link row above a heading. */
export function AuthBackLink({
  label,
  onClick,
}: {
  label: string;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      data-surface
      onClick={onClick}
      className="mb-5 flex cursor-pointer items-center gap-[7px] bg-transparent p-0 text-[12.5px] font-semibold text-muted hover:text-txt3"
    >
      <Icon name="arrowLeft" size={14} strokeWidth={2.4} />
      {label}
    </button>
  );
}

/* ── Fields ──────────────────────────────────────────────────────────────── */

const FIELD_WRAP = [
  "flex items-center gap-2.5 rounded-control-lg border border-bd2 bg-card3 px-[14px] py-[12px]",
  "transition-colors duration-200 focus-within:border-pb",
].join(" ");

const FIELD_INPUT = [
  "min-w-0 flex-1 border-none bg-transparent text-[13.5px] font-medium text-txt outline-none",
  "placeholder:font-normal placeholder:text-faint",
].join(" ");

export interface AuthFieldProps extends InputHTMLAttributes<HTMLInputElement> {
  /** Tracked uppercase label above the field. */
  label: string;
  /** Leading `<Icon />`. */
  icon?: ReactNode;
  /** Rendered to the right of the label, e.g. a "Forgot?" link. */
  labelAction?: ReactNode;
}

export function AuthField({
  label,
  icon,
  labelAction,
  className,
  id,
  ...rest
}: AuthFieldProps) {
  const autoId = useId();
  const inputId = id ?? autoId;
  return (
    <div className="flex flex-col gap-[7px]">
      <div className="flex items-baseline gap-3">
        <label
          htmlFor={inputId}
          className="flex-1 text-[9.5px] font-bold tracking-[.11em] text-label"
        >
          {label}
        </label>
        {labelAction}
      </div>
      <div data-surface className={cn(FIELD_WRAP, className)}>
        {icon && <span className="flex shrink-0 text-faint">{icon}</span>}
        <input id={inputId} className={FIELD_INPUT} {...rest} />
      </div>
    </div>
  );
}

/** Password field with a reveal toggle. Defaults to a lock leading glyph. */
export function AuthPasswordField({
  label,
  icon,
  labelAction,
  className,
  id,
  ...rest
}: AuthFieldProps) {
  const autoId = useId();
  const inputId = id ?? autoId;
  const [shown, setShown] = useState(false);
  return (
    <div className="flex flex-col gap-[7px]">
      <div className="flex items-baseline gap-3">
        <label
          htmlFor={inputId}
          className="flex-1 text-[9.5px] font-bold tracking-[.11em] text-label"
        >
          {label}
        </label>
        {labelAction}
      </div>
      <div data-surface className={cn(FIELD_WRAP, className)}>
        <span className="flex shrink-0 text-faint">
          {icon ?? <Icon name="lock" size={15} strokeWidth={2.2} />}
        </span>
        <input
          id={inputId}
          type={shown ? "text" : "password"}
          className={FIELD_INPUT}
          {...rest}
        />
        <button
          type="button"
          tabIndex={-1}
          data-surface
          aria-label={shown ? "Hide password" : "Show password"}
          onClick={() => setShown((s) => !s)}
          className="flex shrink-0 cursor-pointer bg-transparent p-0 text-faint hover:text-txt3"
        >
          <Icon
            name={shown ? "eyeOff" : "eye"}
            size={16}
            strokeWidth={2.2}
          />
        </button>
      </div>
    </div>
  );
}

export interface CodeFieldProps {
  label: string;
  value: string;
  onChange: (value: string) => void;
  id?: string;
  autoFocus?: boolean;
  disabled?: boolean;
}

/** Six-digit one-time code — wide tracking, numeric only, centred. */
export function CodeField({
  label,
  value,
  onChange,
  id,
  autoFocus,
  disabled,
}: CodeFieldProps) {
  const autoId = useId();
  const inputId = id ?? autoId;
  return (
    <div className="flex flex-col gap-[7px]">
      <label
        htmlFor={inputId}
        className="text-[9.5px] font-bold tracking-[.11em] text-label"
      >
        {label}
      </label>
      <div data-surface className={FIELD_WRAP}>
        <input
          id={inputId}
          inputMode="numeric"
          pattern="[0-9]*"
          autoComplete="one-time-code"
          maxLength={6}
          autoFocus={autoFocus}
          disabled={disabled}
          value={value}
          onChange={(e) => onChange(e.target.value.replace(/\D/g, "").slice(0, 6))}
          placeholder="000000"
          className={cn(
            "min-w-0 flex-1 border-none bg-transparent text-center font-mono text-[20px]",
            "font-bold tracking-[.5em] text-txt outline-none",
            "placeholder:font-normal placeholder:tracking-[.5em] placeholder:text-faint",
          )}
        />
      </div>
    </div>
  );
}

/** The remember-me checkbox. A real control, not a styled div. */
export function AuthCheckbox({
  checked,
  onChange,
  children,
}: {
  checked: boolean;
  onChange: (checked: boolean) => void;
  children: ReactNode;
}) {
  return (
    <label className="flex cursor-pointer items-center gap-[9px] text-[12.5px] text-txt3">
      <button
        type="button"
        role="checkbox"
        aria-checked={checked}
        data-surface
        onClick={() => onChange(!checked)}
        className={cn(
          "flex size-[18px] shrink-0 cursor-pointer items-center justify-center rounded-[6px] border",
          checked
            ? "border-transparent bg-accent-grad text-white"
            : "border-bd2 bg-card3 text-transparent",
        )}
      >
        <Icon name="check" size={12} strokeWidth={3.2} />
      </button>
      {children}
    </label>
  );
}
