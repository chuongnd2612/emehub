// A Settings section that collapses, with a hover lift on the card inside.
//
// Ported from Q-Agent's `components/settings/CollapsibleSection.tsx`, with two
// differences that matter:
//
// 1. **No framer-motion.** EmeHub does not depend on it, and it is not worth
//    adding for one height transition. A CSS `grid-template-rows: 0fr → 1fr`
//    transition animates to the content's real height without measuring it — the
//    trick `height: auto` cannot do.
//
// 2. **Collapsed by default**, where Q-Agent defaults to open. Its comment
//    explains why it chose open (deep-link anchors, discoverability); here the
//    ask was closed, so the section labels carry the discoverability instead.
//
// Q-Agent's hard-won detail is kept: the collapse needs `overflow: hidden`, and
// that **clips the child card's hover-lift shadow** once open. So overflow returns
// to `visible` after the opening transition finishes, and is clipped again the
// moment a collapse starts.
//
// The body stays mounted while collapsed, so an in-progress draft survives being
// collapsed — closing a section must not discard what was typed in it.

import { useRef, useState, type ReactNode } from "react";

import { Icon } from "@/components/ui";
import { cn } from "@/lib/cn";

export function CollapsibleSection({
  title,
  hint,
  defaultOpen = false,
  children,
}: {
  title: string;
  /** Small print beside the title — e.g. that a section applies immediately. */
  hint?: string;
  defaultOpen?: boolean;
  children: ReactNode;
}) {
  const [open, setOpen] = useState(defaultOpen);
  const [clipped, setClipped] = useState(!defaultOpen);
  const timer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);

  const toggle = () => {
    clearTimeout(timer.current);
    const next = !open;
    setOpen(next);
    if (next) {
      // Reveal only once the row has finished growing, or the shadow is clipped
      // mid-animation. Matches the 280ms transition below.
      setClipped(true);
      timer.current = setTimeout(() => setClipped(false), 300);
    } else {
      setClipped(true);
    }
  };

  return (
    <section className="flex flex-col">
      <button
        type="button"
        aria-expanded={open}
        onClick={toggle}
        data-surface
        className="group mb-2.5 flex cursor-pointer items-center gap-2 bg-transparent p-0 text-left"
      >
        <span
          className={cn(
            "flex text-label transition-transform duration-200 group-hover:text-muted",
            open && "rotate-90",
          )}
        >
          <Icon name="chevronRight" size={13} strokeWidth={2.6} />
        </span>
        <span className="text-[11px] font-bold tracking-[.11em] text-label transition-colors group-hover:text-muted">
          {title}
        </span>
        {hint && (
          <span className="text-[11px] font-medium text-faint">{hint}</span>
        )}
      </button>

      {/* grid-template-rows 0fr → 1fr transitions to the content's real height
          without JS measurement. */}
      <div
        // Collapsed content stays MOUNTED so an in-progress draft survives, but
        // must not be interactive: a clipped, zero-height row still swallows
        // clicks aimed at whatever is below it, and its controls would still be
        // tab-reachable. `pointer-events-none` + `aria-hidden` make it inert
        // without unmounting it.
        aria-hidden={!open}
        className={cn(
          "grid transition-[grid-template-rows,opacity] duration-[280ms] ease-[cubic-bezier(.2,.8,.2,1)]",
          open
            ? "grid-rows-[1fr] opacity-100"
            : "pointer-events-none grid-rows-[0fr] opacity-0",
          clipped ? "overflow-hidden" : "overflow-visible",
        )}
      >
        {/* min-h-0 is what lets the 0fr row actually collapse. */}
        <div className="min-h-0">{children}</div>
      </div>
    </section>
  );
}
