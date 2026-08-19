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
  /**
   * The tallest the panel may be here, in px.
   *
   * A panel whose content is longer than either side of the anchor has to
   * scroll; the alternative is what this fixed — a work-item-type list running
   * off the bottom of the window with its last entries unreachable, and no
   * indication that there were any.
   */
  maxHeight: number;
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

/** Kept clear of the viewport edge on every side. */
const MARGIN = 8;

/**
 * The shortest a panel may be squeezed to before scrolling stops helping and it
 * simply reads as broken. Below this it overflows the margin instead, which is
 * the lesser evil for a trigger jammed against an edge.
 */
const MIN_PANEL = 140;

/**
 * Place a `width`×`height` panel below the anchor, flipping above and clamping
 * into the viewport when it would overflow.
 *
 * `height` is what the panel *wants*; the returned `maxHeight` is what it may
 * have. The two differ whenever the content is longer than the space on either
 * side of the anchor — a long list then scrolls inside the panel rather than
 * running off the screen, which is what it used to do: the flip only happened
 * when the panel fitted above *in full*, so a list too tall for either side got
 * neither the flip nor a cap and simply overflowed the bottom of the window.
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
  left = Math.max(MARGIN, Math.min(left, vw - width - MARGIN));

  const roomBelow = vh - anchor.bottom - gap - MARGIN;
  const roomAbove = anchor.top - gap - MARGIN;

  // Prefer below, flip when it fits above, and when it fits neither take the
  // roomier side and scroll. Deciding by "which side is roomier" rather than by
  // "does it fit" is what keeps a nearly-fitting list from being cut in half.
  const flip = height > roomBelow && (height <= roomAbove || roomAbove > roomBelow);
  const room = flip ? roomAbove : roomBelow;
  const maxHeight = Math.max(MIN_PANEL, Math.min(height, room));

  const top = flip
    ? Math.max(MARGIN, anchor.top - gap - maxHeight)
    : anchor.bottom + gap;

  const originX = align === "end" ? "right" : align === "center" ? "center" : "left";
  return {
    top,
    left,
    maxHeight,
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
