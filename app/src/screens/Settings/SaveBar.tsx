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

import { Icon } from "@/components/ui";
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

  return (
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
    </div>
  );
}
