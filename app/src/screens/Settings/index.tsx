// Handoff § 10. Settings — max-width 1080px.
//
// Mirrors Q-Agent's Settings: collapsible sections with a hover lift on each
// card. Sections start **collapsed** (Q-Agent defaults to open; the ask here was
// closed).
//
// ## Everything here applies immediately
//
// Q-Agent's Settings is a bulk-save form: controls mutate a draft and nothing is
// written until a save bar's Save. EmeHub no longer has one, and that is a
// consequence rather than a choice — the two sections that fed the draft
// (Workspace defaults, Notifications) are gone (#191). They wrote a default
// provider, a default agent, a knowledge scope and three notification switches
// to localStorage, and **nothing in the app ever read any of them back**: no
// screen consulted the defaults, and the hub has no notification delivery at
// all. With them removed the draft has no fields, so a save bar would have been
// a button that saves nothing — the same lie in a different shape.
//
// What remains applies the moment it changes, which was always right for both:
// a theme picker you cannot preview is worse than one that saves immediately,
// and product availability is a live gate (#186) whose whole point is taking
// effect on the next request.

import { AppearanceCard } from "./AppearanceCard";
import { CollapsibleSection } from "./CollapsibleSection";
import { ProductAvailabilityCard } from "./ProductAvailabilityCard";

/** Hover lift, matching Q-Agent's rows: raise plus an expanded shadow. */
const LIFT =
  "transition-[transform,box-shadow,border-color] duration-[250ms] ease-[cubic-bezier(.2,.8,.2,1)] hover:-translate-y-1 hover:shadow-pop";

export default function SettingsScreen() {
  return (
    <div className="animate-fade-in-up flex max-w-[1080px] flex-col gap-[18px]">
      <CollapsibleSection title="APPEARANCE" hint="applies immediately">
        <div className={LIFT}>
          <AppearanceCard />
        </div>
      </CollapsibleSection>

      <CollapsibleSection title="PRODUCT AVAILABILITY" hint="applies immediately">
        <div className={LIFT}>
          <ProductAvailabilityCard />
        </div>
      </CollapsibleSection>
    </div>
  );
}
