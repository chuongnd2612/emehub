// Handoff › 4. Tickets ("dropdown 250px, var(--pop), radius 13, headed TICKET
// SOURCE, green check on the active item"), Overlays ("every dropdown closes on
// scrim click, Esc, and when another one opens") and Motion (`scaleIn .15s`
// with transform-origin at the trigger corner).
//
// Rendered via createPortal to document.body with FIXED positioning anchored to
// the trigger's rect — ancestor backdrop-filter traps z-index (CLAUDE.md).

import {
  useCallback,
  useEffect,
  useRef,
  type ReactNode,
} from "react";
import { createPortal } from "react-dom";
import { cn } from "@/lib/cn";
import {
  placeBelow,
  useAnchorRect,
  useEscape,
  type AnchorAlign,
} from "@/hooks/useAnchoredPosition";
import { useUi } from "@/store/ui";
import { Icon } from "./Icon";

export interface DropdownItem<T extends string = string> {
  value: T;
  label: ReactNode;
  /** Optional leading glyph. */
  icon?: ReactNode;
  /** Renders in rose and is separated from the group above. */
  destructive?: boolean;
  disabled?: boolean;
}

export interface DropdownProps<T extends string = string> {
  /**
   * Unique key for this dropdown. Opening one closes every other — the store
   * holds a single `dd` key (Handoff › Interactions › Navigation).
   */
  ddKey: string;
  /** The trigger. Receives the ref + open state via a render prop. */
  trigger: (args: {
    ref: React.RefObject<HTMLButtonElement | null>;
    open: boolean;
    toggle: () => void;
  }) => ReactNode;
  items: DropdownItem<T>[];
  /** Currently selected value — rendered with a green check. */
  value?: T | null;
  onSelect: (value: T) => void;
  /** Small tracked uppercase heading, e.g. `TICKET SOURCE`. */
  heading?: string;
  /** Panel width in px. 250 for the source picker; menus are narrower. */
  width?: number;
  align?: AnchorAlign;
  className?: string;
}

export function Dropdown<T extends string = string>({
  ddKey,
  trigger,
  items,
  value,
  onSelect,
  heading,
  width = 250,
  align = "start",
  className,
}: DropdownProps<T>) {
  const dd = useUi((s) => s.dd);
  const toggleDd = useUi((s) => s.toggleDd);
  const setDd = useUi((s) => s.setDd);
  const open = dd === ddKey;

  const triggerRef = useRef<HTMLButtonElement>(null);
  const panelRef = useRef<HTMLDivElement>(null);
  const anchor = useAnchorRect(triggerRef, open);

  const close = useCallback(() => setDd(null), [setDd]);
  useEscape(open, close);

  // Outside click. A capture-phase listener so it fires before the trigger's
  // own onClick would immediately reopen the panel.
  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => {
      const t = e.target as Node;
      if (panelRef.current?.contains(t)) return;
      if (triggerRef.current?.contains(t)) return;
      close();
    };
    document.addEventListener("mousedown", onDown, true);
    return () => document.removeEventListener("mousedown", onDown, true);
  }, [open, close]);

  const estimatedHeight =
    items.length * 36 + (heading ? 30 : 0) + 12;
  const pos = anchor
    ? placeBelow(anchor, width, estimatedHeight, align)
    : null;

  return (
    <>
      {trigger({ ref: triggerRef, open, toggle: () => toggleDd(ddKey) })}
      {open &&
        pos &&
        createPortal(
          <div
            ref={panelRef}
            role="listbox"
            className={cn(
              // Scrolls vertically, never horizontally: a long list has to be
              // reachable, and a sideways scrollbar under a menu is always a
              // layout bug rather than a feature.
              "fixed z-[1000] animate-scale-in overflow-x-hidden overflow-y-auto",
              "rounded-[13px] border border-bd2 bg-pop p-1.5 shadow-pop",
              className,
            )}
            style={{
              top: pos.top,
              left: pos.left,
              width,
              maxHeight: pos.maxHeight,
              transformOrigin: pos.transformOrigin,
            }}
          >
            {heading && (
              <div className="px-2.5 pt-1.5 pb-2 text-[9.5px] font-bold tracking-[.12em] text-label">
                {heading}
              </div>
            )}
            {items.map((item) => {
              const selected = value != null && item.value === value;
              return (
                <button
                  key={item.value}
                  type="button"
                  role="option"
                  aria-selected={selected}
                  disabled={item.disabled}
                  onClick={() => {
                    onSelect(item.value);
                    close();
                  }}
                  className={cn(
                    "flex w-full cursor-pointer items-center gap-2.5 rounded-control px-2.5 py-2",
                    "text-left text-[12.5px] font-semibold transition-colors duration-200",
                    item.destructive
                      ? "text-danger hover:bg-danger-tint"
                      : "text-txt3 hover:bg-card3 hover:text-txt2",
                    item.disabled && "cursor-not-allowed opacity-50",
                  )}
                >
                  {item.icon}
                  <span className="min-w-0 flex-1 truncate">{item.label}</span>
                  {selected && (
                    <span className="flex shrink-0 text-ok">
                      <Icon name="check" size={14} strokeWidth={2.6} />
                    </span>
                  )}
                </button>
              );
            })}
          </div>,
          document.body,
        )}
    </>
  );
}
