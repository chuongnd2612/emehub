// Handoff § 10. Settings — max-width 1080px.
//
// Mirrors Q-Agent's Settings: collapsible sections, a hover lift on each card,
// and **bulk save** — controls mutate a draft and nothing is written until the
// save bar's Save. Sections start **collapsed** (Q-Agent defaults to open; the ask
// here was closed).
//
// ## Appearance is deliberately outside the draft
//
// Mode, accent, bloom and depth apply the moment they change, and that is correct:
// a theme picker you cannot preview is worse than one that saves immediately. It
// writes straight to `store/appearance`, and the section label says so rather than
// leaving the inconsistency to be discovered.
//
// ## Where the rest is saved
//
// The hub has no preferences endpoint, so Workspace defaults and Notifications
// persist to localStorage via `store/preferences` — per-browser, and labelled as
// such. A stated compromise: leaving them in screen state would have made Save a
// control that saves nothing, and calling an invented `PUT /preferences` would
// simply fail.

import { useMemo, useState } from "react";
import { useShallow } from "zustand/react/shallow";

import { toast } from "@/components/ui";
import {
  readPreferences,
  usePreferences,
  type Preferences,
} from "@/store/preferences";

import { AppearanceCard } from "./AppearanceCard";
import { CollapsibleSection } from "./CollapsibleSection";
import { NotificationsCard } from "./NotificationsCard";
import { ProductAvailabilityCard } from "./ProductAvailabilityCard";
import { SaveBar } from "./SaveBar";
import { WorkspaceDefaultsCard } from "./WorkspaceDefaultsCard";

/** Hover lift, matching Q-Agent's rows: raise plus an expanded shadow. */
const LIFT =
  "transition-[transform,box-shadow,border-color] duration-[250ms] ease-[cubic-bezier(.2,.8,.2,1)] hover:-translate-y-1 hover:shadow-pop";

export default function SettingsScreen() {
  /**
   * `useShallow` is load-bearing, not decoration. `readPreferences` builds a new
   * object on every store read, so without a shallow comparison zustand's
   * `useSyncExternalStore` sees a changed snapshot every render and loops until
   * React throws "Maximum update depth exceeded" — which is exactly what it did.
   */
  const saved = usePreferences(useShallow(readPreferences));
  const save = usePreferences((s) => s.save);

  const [draft, setDraft] = useState<Preferences>(saved);
  const [saving, setSaving] = useState(false);

  const change = (patch: Partial<Preferences>) =>
    setDraft((d) => ({ ...d, ...patch }));

  /**
   * How many fields differ from what is saved.
   *
   * A count rather than a boolean because the save bar shows it, and "3 unsaved
   * changes" is more useful than "unsaved changes" — it also makes an accidental
   * edit in a collapsed section visible instead of silent.
   */
  const dirtyCount = useMemo(
    () =>
      (Object.keys(draft) as (keyof Preferences)[]).filter(
        (key) => draft[key] !== saved[key],
      ).length,
    [draft, saved],
  );

  const commit = () => {
    setSaving(true);
    save(draft);
    setSaving(false);
    toast("Settings saved");
  };

  return (
    <>
      <div className="animate-fade-in-up flex max-w-[1080px] flex-col gap-[18px]">
        <CollapsibleSection title="APPEARANCE" hint="applies immediately">
          <div className={LIFT}>
            <AppearanceCard />
          </div>
        </CollapsibleSection>

        <CollapsibleSection title="WORKSPACE DEFAULTS">
          <div className={LIFT}>
            <WorkspaceDefaultsCard draft={draft} onChange={change} />
          </div>
        </CollapsibleSection>

        <CollapsibleSection title="PRODUCT AVAILABILITY" hint="applies immediately">
          <div className={LIFT}>
            <ProductAvailabilityCard />
          </div>
        </CollapsibleSection>

        <CollapsibleSection title="NOTIFICATIONS">
          <div className={LIFT}>
            <NotificationsCard draft={draft} onChange={change} />
          </div>
        </CollapsibleSection>

        {/* Room so the fixed save bar cannot cover the last control. Sized to
            clear the bar itself (~48px) plus its 24px bottom padding — 40px was
            not enough, and the bar sat over the last toggle. */}
        <div className="h-24 shrink-0" aria-hidden />
      </div>

      <SaveBar
        count={dirtyCount}
        saving={saving}
        onDiscard={() => setDraft(saved)}
        onSave={commit}
      />
    </>
  );
}
