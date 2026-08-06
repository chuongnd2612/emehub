// Handoff § 10. Settings › Workspace defaults — three rows, each a label +
// description + chip group.
//
// State Management groups these as `defProvider` / `defAgent` / `defScope`.
//
// The card is now CONTROLLED by the Settings screen's draft — it no longer holds
// its own state, because these save in bulk from the save bar rather than on every
// click. Where the values live and why they are per-browser is explained in
// `store/preferences.ts`.

import { GlassCard } from "@/components/ui";
import type { Preferences } from "@/store/preferences";
import { OptionChip } from "./SettingRow";

interface DefaultRow {
  key: "defProvider" | "defAgent" | "defScope";
  label: string;
  description: string;
  options: string[];
}

const ROWS: DefaultRow[] = [
  {
    key: "defProvider",
    label: "Default provider",
    description: "Where new projects look for work items first.",
    options: ["Azure DevOps", "Jira", "GitHub"],
  },
  {
    key: "defAgent",
    label: "Default agent",
    description: "The agent wired to a project the moment it is created.",
    options: ["Q-Agent", "D-Agent", "None"],
  },
  {
    key: "defScope",
    label: "Knowledge scope",
    description:
      "Whether a new knowledge source is shared or kept to its project.",
    options: ["Per project", "Workspace"],
  },
];

export function WorkspaceDefaultsCard({
  draft,
  onChange,
}: {
  draft: Preferences;
  onChange: (patch: Partial<Preferences>) => void;
}) {

  return (
    <GlassCard radius="panel" className="flex flex-col gap-4 p-[22px]">
      <div>
        <div className="text-[15px] font-extrabold tracking-[-.01em] text-txt">
          Workspace defaults
        </div>
        <div className="mt-1 text-[12.5px] text-muted">
          Applied to every new project unless the project overrides them.
        </div>
      </div>

      {ROWS.map((row) => (
        <div
          key={row.key}
          className="flex flex-wrap items-center gap-4 border-t border-bd3 pt-[14px]"
        >
          <div className="min-w-[200px] flex-1">
            <div className="text-[13.5px] font-bold text-txt2">{row.label}</div>
            <div className="mt-[3px] text-[12px] leading-[1.5] text-muted">
              {row.description}
            </div>
          </div>
          <div className="flex flex-wrap gap-[7px]">
            {row.options.map((option) => (
              <OptionChip
                key={option}
                label={option}
                active={draft[row.key] === option}
                onClick={() => onChange({ [row.key]: option })}
              />
            ))}
          </div>
        </div>
      ))}
    </GlassCard>
  );
}
