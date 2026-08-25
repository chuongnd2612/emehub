// The unsaved-changes bar — ported from Q-Agent's Settings
// (`screens/Settings.tsx`): fixed to the bottom, visible only while dirty,
// carrying the count, Discard and Save.
//
// **Opaque background, no `backdrop-filter`.** It layers over the animated
// constellation, where a filter is both a compositing artifact and a
// stacking-context trap (CLAUDE.md › Frontend conventions). This is the exact
// case that rule was written for.
//
// The wrapper is `pointer-events-none` so the bar never blocks clicks on the page
// behind it; only the pill itself takes pointer events.
//
// **Portalled to `document.body`, and it has to be.** `position: fixed` is
// resolved against the nearest ancestor with a `transform`, `filter` or
// `backdrop-filter` rather than against the viewport, and every screen that
// wants this bar sits inside one: the shell's screens open with
// `animate-fade-in-up`, whose `both` fill-mode leaves `transform: matrix(…)`
// applied for the lifetime of the element. Rendered in place, the bar was
// pinned to the bottom of a 1507 px-tall screen container and never appeared on
// screen at all — the same stacking-context trap CLAUDE.md documents for
// dropdowns and popovers, in its `position: fixed` form. Only the mount point
// moves; the markup below is unchanged.

import { createPortal } from "react-dom";

import { Icon } from "./Icon";
import { cn } from "@/lib/cn";

export function SaveBar({
  count,
  saving,
  onDiscard,
  onSave,
}: {
  /** How many fields differ from what is saved. */
  count: number;
  saving: boolean;
  onDiscard: () => void;
  onSave: () => void;
}) {
  if (count === 0) return null;

  return createPortal(
    <div className="pointer-events-none fixed inset-x-0 bottom-0 z-[900] flex justify-center px-4 pb-6">
      <div
        role="status"
        className={cn(
          "animate-fade-in-up pointer-events-auto flex items-center gap-3 rounded-card-lg",
          "border border-bd2 bg-pop px-5 py-3 shadow-pop",
        )}
      >
        <span className="flex size-[22px] shrink-0 items-center justify-center rounded-full bg-warn-tint text-warn">
          <Icon name="alert" size={13} strokeWidth={2.4} />
        </span>
        <span className="text-[12.5px] font-semibold text-txt2">
          {count} unsaved {count === 1 ? "change" : "changes"}
        </span>

        <button
          type="button"
          onClick={onDiscard}
          disabled={saving}
          className={cn(
            "cursor-pointer rounded-control-lg border border-bd2 bg-card3 px-[15px] py-[9px]",
            "text-[12.5px] font-semibold text-txt2 transition-colors hover:bg-bd2",
            "disabled:cursor-not-allowed disabled:opacity-50",
          )}
        >
          Discard
        </button>
        <button
          type="button"
          onClick={onSave}
          disabled={saving}
          className={cn(
            "bg-accent-grad cursor-pointer rounded-control-lg px-[17px] py-[9px]",
            "text-[12.5px] font-bold text-p-on transition-opacity hover:opacity-90",
            "disabled:cursor-not-allowed disabled:opacity-50",
          )}
        >
          {saving ? "Saving…" : "Save changes"}
        </button>
      </div>
    </div>,
    document.body,
  );
}
