// Handoff § 0. App shell › Page header. Children, in order:
//   1. title block  — flex:1 1 190px; min-width:0; overflow:hidden
//   2. palette button — flex:0 1 320px; min-width:130px; margin-left:auto
//   3. 1px x 26px divider
//   4. Claude credential chip (opens the credential popover)
//   5. dark/light toggle — 38px square
//   6. bell — 38px square with a 6px accent dot
//
// ⚠️ The TITLE is the flexible item and MUST truncate first, or it overlaps the
// search field at narrow widths. The handoff calls this out explicitly; it is
// why the title block carries `flex-[1_1_190px] min-w-0` and the palette button
// `flex-[0_1_320px]` rather than the other way round.

import { ClaudeCredentialChip } from "@/components/overlays";
import { Icon, toast } from "@/components/ui";
import { cn } from "@/lib/cn";
import { useAppearance } from "@/store/appearance";
import { useUi } from "@/store/ui";
import { useHeaderContent } from "./HeaderContext";

const SQUARE = cn(
  "relative flex size-[38px] shrink-0 cursor-pointer items-center justify-center",
  "rounded-[12px] border border-bd2 bg-card2 hover:bg-bd",
);

export function PageHeader() {
  const { title, subtitle } = useHeaderContent();
  const mode = useAppearance((s) => s.mode);
  const toggleMode = useAppearance((s) => s.toggleMode);
  const setPaletteOpen = useUi((s) => s.setPaletteOpen);
  const setClaudeOpen = useUi((s) => s.setClaudeOpen);

  const openPalette = () => {
    // Every dropdown/popover closes when another overlay opens.
    setClaudeOpen(false);
    setPaletteOpen(true);
  };

  return (
    <header
      className={cn(
        "flex shrink-0 items-center gap-3 px-[18px] py-3.5",
        "glass-panel rounded-[20px] shadow-panel",
      )}
    >
      {/* 1. Title block. */}
      <div className="flex-[1_1_190px] overflow-hidden">
        <div className="truncate text-[19px] font-black tracking-[-.03em] text-txt">
          {title}
        </div>
        <div className="mt-0.5 truncate text-[12px] text-faint">{subtitle}</div>
      </div>

      {/* 2. Command-palette button. */}
      <button
        type="button"
        data-surface
        onClick={openPalette}
        className={cn(
          "ml-auto flex flex-[0_1_320px] cursor-pointer items-center gap-2.5",
          "min-w-[130px] rounded-[13px] border border-bd2 bg-card2 px-3.5 py-2.5 hover:bg-bd3",
        )}
      >
        <Icon
          name="search"
          size={15}
          strokeWidth={2.2}
          className="shrink-0 text-faint"
        />
        <span className="min-w-0 flex-1 truncate text-left text-[13px] text-faint">
          Search projects, tickets, knowledge…
        </span>
        <span className="shrink-0 rounded-[7px] border border-bd2 bg-bd3 px-[7px] py-[3px] font-mono text-[10.5px] font-semibold text-muted">
          ⌘K
        </span>
      </button>

      {/* 3. Divider. */}
      <div className="h-[26px] w-px shrink-0 bg-bd2" />

      {/* 4. Claude credential chip + popover. */}
      <ClaudeCredentialChip />

      {/* 5. Dark / light toggle. */}
      <button
        type="button"
        data-surface
        onClick={toggleMode}
        title={mode === "light" ? "Switch to dark mode" : "Switch to light mode"}
        aria-label={
          mode === "light" ? "Switch to dark mode" : "Switch to light mode"
        }
        className={cn(SQUARE, "text-txt2")}
      >
        <Icon
          name={mode === "light" ? "sun" : "moon"}
          size={16}
          strokeWidth={2.1}
        />
      </button>

      {/* 6. Bell. */}
      <button
        type="button"
        data-surface
        aria-label="Notifications"
        onClick={() =>
          toast(
            "3 notifications",
            "GitHub needs re-auth · 2 syncs finished",
            "info",
          )
        }
        className={cn(SQUARE, "text-txt3")}
      >
        <Icon name="bell" size={16} strokeWidth={2.1} />
        <span className="absolute top-2 right-[9px] size-1.5 rounded-full bg-pl shadow-[0_0_7px_var(--pl)]" />
      </button>
    </header>
  );
}
