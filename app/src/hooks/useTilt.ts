// Handoff › "Motion — pointer-driven (JS)".
//
// Two pointer-tilt behaviours, both gated by the *Depth on hover* setting
// (appearance.tilt). When the setting is off both hooks return no-op handlers
// and never touch the element.
//
// These are the ONLY places an inline `transform` is legitimate — the value is
// genuinely dynamic (Handoff rule: no inline styles except computed values).

import { useCallback, useRef, type MouseEvent as ReactMouseEvent } from "react";
import { useAppearance } from "@/store/appearance";

const TILT_TRANSITION = "transform .35s cubic-bezier(.2,.7,.3,1)";

export interface TiltHandlers<T extends HTMLElement = HTMLDivElement> {
  /** Attach to the element that should tilt. */
  ref: React.RefObject<T | null>;
  /** Spread onto the element (or its perspective wrapper). */
  onMouseMove: (e: ReactMouseEvent<HTMLElement>) => void;
  onMouseLeave: () => void;
  /** True when the Depth-on-hover setting is on. */
  enabled: boolean;
}

/**
 * Logo tilt — `perspective(820px) rotateX((0.5-py)*16deg)
 * rotateY((px-0.5)*24deg) scale(1.06)`, reset to a flat scale(1) on leave.
 * The wrapper the handlers sit on should carry `perspective: 820px`.
 */
export function useLogoTilt<
  T extends HTMLElement = HTMLDivElement,
>(): TiltHandlers<T> {
  const enabled = useAppearance((s) => s.tilt);
  const ref = useRef<T>(null);

  const onMouseMove = useCallback(
    (e: ReactMouseEvent<HTMLElement>) => {
      const el = ref.current;
      if (!enabled || !el) return;
      const r = e.currentTarget.getBoundingClientRect();
      const px = (e.clientX - r.left) / r.width;
      const py = (e.clientY - r.top) / r.height;
      el.style.transition = TILT_TRANSITION;
      el.style.transform = `perspective(820px) rotateX(${(0.5 - py) * 16}deg) rotateY(${
        (px - 0.5) * 24
      }deg) scale(1.06)`;
    },
    [enabled],
  );

  const onMouseLeave = useCallback(() => {
    const el = ref.current;
    if (!el) return;
    el.style.transition = TILT_TRANSITION;
    el.style.transform = "perspective(820px) rotateX(0deg) rotateY(0deg) scale(1)";
  }, []);

  return { ref, onMouseMove, onMouseLeave, enabled };
}

/**
 * Card tilt — `perspective(1100px) rotateX((0.5-py)*9deg)
 * rotateY((px-0.5)*11deg) translateY(-5px)`, plus `--gx` / `--gy` set to the
 * cursor position as a percentage so a `radial-gradient(... at var(--gx)
 * var(--gy) ...)` highlight wash follows the pointer.
 */
export function useCardTilt<
  T extends HTMLElement = HTMLDivElement,
>(): TiltHandlers<T> {
  const enabled = useAppearance((s) => s.tilt);
  const ref = useRef<T>(null);

  const onMouseMove = useCallback(
    (e: ReactMouseEvent<HTMLElement>) => {
      const el = ref.current;
      if (!el) return;
      const r = e.currentTarget.getBoundingClientRect();
      const px = (e.clientX - r.left) / r.width;
      const py = (e.clientY - r.top) / r.height;
      // The highlight wash tracks the cursor even with depth off — only the
      // 3D rotation is gated by the setting.
      el.style.setProperty("--gx", `${px * 100}%`);
      el.style.setProperty("--gy", `${py * 100}%`);
      if (!enabled) return;
      el.style.transition = TILT_TRANSITION;
      el.style.transform = `perspective(1100px) rotateX(${(0.5 - py) * 9}deg) rotateY(${
        (px - 0.5) * 11
      }deg) translateY(-5px)`;
    },
    [enabled],
  );

  const onMouseLeave = useCallback(() => {
    const el = ref.current;
    if (!el) return;
    el.style.transition = TILT_TRANSITION;
    el.style.transform =
      "perspective(1100px) rotateX(0deg) rotateY(0deg) translateY(0)";
    el.style.removeProperty("--gx");
    el.style.removeProperty("--gy");
  }, []);

  return { ref, onMouseMove, onMouseLeave, enabled };
}
