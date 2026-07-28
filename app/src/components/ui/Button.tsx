// Handoff › Motion — transitions ("transform .18s on primary buttons,
// translateY(-1px|-2px)") and Spacing/radius/elevation ("primary buttons
// 0 8px 20px -6px var(--pglow)", "button radius 11–14").

import type { ButtonHTMLAttributes, ReactNode } from "react";
import { cn } from "@/lib/cn";

export type ButtonVariant =
  /** Accent gradient fill + glow. The one call to action per view. */
  | "primary"
  /** Inset surface + hairline border. The default secondary action. */
  | "ghost"
  /** Accent tint + accent border — "Add connection", chosen source cards. */
  | "tinted"
  /** 1.5px dashed accent border on an accent tint — empty-state CTAs. */
  | "dashed"
  /** Rose text/border. Remove, revoke, delete. */
  | "destructive";

export type ButtonSize = "sm" | "md" | "lg";

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  size?: ButtonSize;
  /** Icon element rendered before the label. */
  icon?: ReactNode;
  /** Icon element rendered after the label. */
  trailingIcon?: ReactNode;
  /** Renders a square icon-only control (38px at `md`). */
  iconOnly?: boolean;
  children?: ReactNode;
}

const VARIANT: Record<ButtonVariant, string> = {
  primary:
    "bg-accent-grad text-white border border-transparent shadow-primary hover:-translate-y-px active:translate-y-0",
  ghost:
    "bg-inset border border-bd2 text-txt3 hover:bg-bd3 hover:text-txt2",
  tinted: "bg-pt border border-pb text-p-on hover:bg-pb/40",
  dashed:
    "bg-pt border-[1.5px] border-dashed border-pb text-p-on hover:bg-pb/30",
  destructive:
    "bg-danger-tint border border-danger/30 text-danger hover:bg-danger/20",
};

const SIZE: Record<ButtonSize, string> = {
  sm: "h-8 px-3 text-[12px] rounded-control-lg gap-1.5",
  md: "h-9 px-4 text-[12.5px] rounded-control-lg gap-2",
  lg: "h-[46px] px-6 text-[15px] rounded-button-lg gap-2.5",
};

const ICON_ONLY: Record<ButtonSize, string> = {
  sm: "h-8 w-8 p-0 rounded-control-lg",
  md: "h-[38px] w-[38px] p-0 rounded-control-lg",
  lg: "h-[46px] w-[46px] p-0 rounded-button-lg",
};

export function Button({
  variant = "ghost",
  size = "md",
  icon,
  trailingIcon,
  iconOnly = false,
  className,
  children,
  type = "button",
  ...rest
}: ButtonProps) {
  return (
    <button
      type={type}
      data-surface
      className={cn(
        "inline-flex shrink-0 cursor-pointer items-center justify-center font-bold",
        "transition-[background-color,border-color,color,transform,box-shadow] duration-200",
        "disabled:cursor-not-allowed disabled:opacity-50 disabled:hover:translate-y-0",
        VARIANT[variant],
        iconOnly ? ICON_ONLY[size] : SIZE[size],
        className,
      )}
      {...rest}
    >
      {icon}
      {!iconOnly && children}
      {trailingIcon}
    </button>
  );
}
