// Fixed-position anchoring for portalled overlays.
//
// CLAUDE.md › Frontend conventions: floating overlays render via a portal to
// document.body with FIXED positioning anchored to the trigger's bounding rect,
// because ancestor backdrop-filter / transform / filter create stacking
// contexts that trap child z-index. Every glass panel in EmeHub has a
// backdrop-filter, so this is not optional here.

import { useCallback, useEffect, useLayoutEffect, useState } from "react";

export interface AnchorRect {
  top: number;
  left: number;
  right: number;
  bottom: number;
  width: number;
  height: number;
}

export type AnchorAlign = "start" | "end" | "center";

export interface AnchoredPosition {
  top: number;
  left: number;
  /** `transform-origin` for the `scaleIn` entrance (the trigger's corner). */
  transformOrigin: string;
}

/**
 * Track a trigger element's viewport rect while `open`, recomputing on scroll
 * and resize so the panel stays glued to it.
 */
export function useAnchorRect(
  triggerRef: React.RefObject<HTMLElement | null>,
  open: boolean,
): AnchorRect | null {
  const [rect, setRect] = useState<AnchorRect | null>(null);

  const measure = useCallback(() => {
    const el = triggerRef.current;
    if (!el) return;
    const r = el.getBoundingClientRect();
    setRect({
      top: r.top,
      left: r.left,
      right: r.right,
      bottom: r.bottom,
      width: r.width,
      height: r.height,
    });
  }, [triggerRef]);

  useLayoutEffect(() => {
    if (!open) return;
    measure();
  }, [open, measure]);

  useEffect(() => {
    if (!open) return;
    const onChange = () => measure();
    window.addEventListener("scroll", onChange, true);
    window.addEventListener("resize", onChange);
    return () => {
      window.removeEventListener("scroll", onChange, true);
      window.removeEventListener("resize", onChange);
    };
  }, [open, measure]);

  return rect;
}

/**
 * Place a `width`×`height` panel below the anchor, flipping above and clamping
 * into the viewport when it would overflow.
 */
export function placeBelow(
  anchor: AnchorRect,
  width: number,
  height: number,
  align: AnchorAlign = "start",
  gap = 6,
): AnchoredPosition {
  const vw = window.innerWidth;
  const vh = window.innerHeight;

  let left =
    align === "end"
      ? anchor.right - width
      : align === "center"
        ? anchor.left + anchor.width / 2 - width / 2
        : anchor.left;
  left = Math.max(8, Math.min(left, vw - width - 8));

  const below = anchor.bottom + gap;
  const flip = below + height > vh - 8 && anchor.top - gap - height > 8;
  const top = flip ? anchor.top - gap - height : below;

  const originX = align === "end" ? "right" : align === "center" ? "center" : "left";
  return {
    top,
    left,
    transformOrigin: `${originX} ${flip ? "bottom" : "top"}`,
  };
}

/** Close on Esc while `open`. */
export function useEscape(open: boolean, onClose: () => void) {
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.stopPropagation();
        onClose();
      }
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open, onClose]);
}
