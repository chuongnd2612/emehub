// Handoff § 10. Settings › Notifications — three toggle rows.
//
// State Management groups these as `notifImport` / `notifCred` / `notifRuns`;
// the prototype's defaults are on / on / off.
//
// CONTROLLED by the Settings screen's draft — these commit from the save bar, not
// on every flip. See `store/preferences.ts` for where they end up and why they are
// per-browser for now.

import { GlassCard } from "@/components/ui";
import type { Preferences } from "@/store/preferences";
import { ToggleRow } from "./SettingRow";

interface NotificationRow {
  key: "notifImport" | "notifCred" | "notifRuns";
  label: string;
  description: string;
}

const ROWS: NotificationRow[] = [
  {
    key: "notifImport",
    label: "Failed imports",
    description: "Alert when a provider import fails or partially completes.",
  },
  {
    key: "notifCred",
    label: "Credential expiry",
    description:
      "Warn three days before a shared or personal Claude token expires.",
  },
  {
    key: "notifRuns",
    label: "Every agent run",
    description:
      "A notification each time Q-Agent or D-Agent finishes. Noisy by design.",
  },
];

export function NotificationsCard({
  draft,
  onChange,
}: {
  draft: Preferences;
  onChange: (patch: Partial<Preferences>) => void;
}) {

  return (
    <GlassCard radius="panel" className="flex flex-col gap-[2px] p-[22px]">
      <div className="mb-[10px]">
        <div className="text-[15px] font-extrabold tracking-[-.01em] text-txt">
          Notifications
        </div>
        <div className="mt-1 text-[12.5px] text-muted">
          What EmeHub tells you about, and what it keeps quiet.
        </div>
      </div>

      {ROWS.map((row) => (
        <ToggleRow
          key={row.key}
          label={row.label}
          description={row.description}
          checked={draft[row.key]}
          onChange={(checked) => onChange({ [row.key]: checked })}
          className="border-t border-bd3 py-[15px]"
        />
      ))}
    </GlassCard>
  );
}
