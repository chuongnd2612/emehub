// NO DESIGN WAS SUPPLIED FOR THIS SCREEN.
//
// The handoff defines `Live` / `Placeholder` badges on the product cards but no
// state for a product that has been turned off (#186). This follows the same
// shape as `SignedOut` — glyph, one line, a single primary action — which is the
// empty-state voice CLAUDE.md specifies, in EmeHub's token language.
//
// Public on purpose. Someone who follows a link to a product that is not open
// yet may have no hub session at all, and bouncing them to /login to be told
// "coming soon" would answer a question they did not ask.
//
// The edge proxy sends them here: it asks `GET /agents/{key}/open` before letting
// a browser through to an agent, and redirects on a refusal. The agent itself is
// never modified for this — a hub decision must not need a release of two other
// applications to take effect.

import { useNavigate, useParams } from "react-router-dom";

import { AuthLayout } from "@/components/auth/AuthLayout";
import { Button, Icon } from "@/components/ui";

/** Display names for the agents this page can speak for. An unknown key still
 *  renders — the page's job is to say "not yet", and it can do that without
 *  knowing which product the caller meant. */
const NAMES: Record<string, string> = {
  qagent: "Q-Agent",
  dagent: "D-Agent",
};

export function ComingSoonScreen() {
  const navigate = useNavigate();
  const { key = "" } = useParams();
  const name = NAMES[key] ?? "This product";

  return (
    <AuthLayout>
      <div className="flex flex-col items-center gap-[9px] px-2 py-6 text-center">
        <span className="animate-scale-in mb-2 flex size-[60px] items-center justify-center rounded-[19px] bg-accent-grad text-white shadow-primary">
          <Icon name="spark" size={26} strokeWidth={2.2} />
        </span>

        <h1 className="m-0 text-[23px] leading-tight font-black tracking-[-.035em] text-txt">
          {name} is coming soon
        </h1>
        <p className="m-0 mb-4 max-w-[42ch] text-[12.5px] leading-[1.55] text-pretty text-muted">
          It is not open yet. Everything else in EmeHub keeps working, and this
          page will turn into the product the moment it is switched on.
        </p>

        <Button variant="primary" size="lg" className="w-full" onClick={() => navigate("/")}>
          Back to EmeHub
        </Button>
      </div>
    </AuthLayout>
  );
}

export default ComingSoonScreen;
