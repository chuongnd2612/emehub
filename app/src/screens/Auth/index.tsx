// Handoff § 7. Authentication (`/app/auth`).
//
// The handoff has four tabs: Single sign-on · Sessions · API keys · Login
// providers. **Two are gone.**
//
// `Single sign-on` hardcoded an entity id, an ACS URL, a certificate expiry and a
// seven-bar sign-ins chart; `API keys` listed three `ehk_live_…` keys with usage
// times. The hub has neither feature — no endpoint, no model, no config — so both
// tabs were pure invention, and a tab leading to a feature that does not exist is
// the same lying-control problem the ticket filters already refuse. They come back
// with the features, not before.
//
// The active tab is intra-screen SELECTION, so it lives in the URL as `?tab=`
// — not in Zustand (CLAUDE.md › Frontend conventions).

import { useSearchParams } from "react-router-dom";
import { LoginProvidersPanel } from "./LoginProvidersPanel";
import { SessionsPanel } from "./SessionsPanel";
import { TabStrip } from "./TabStrip";

const TABS = [
  { value: "sessions", label: "Sessions" },
  { value: "providers", label: "Login providers" },
] as const;

type AuthTab = (typeof TABS)[number]["value"];

const isTab = (value: string | null): value is AuthTab =>
  TABS.some((t) => t.value === value);

export default function AuthScreen() {
  const [params, setParams] = useSearchParams();
  const raw = params.get("tab");
  // A bookmarked `?tab=sso` or `?tab=keys` lands on Sessions rather than blank.
  const tab: AuthTab = isTab(raw) ? raw : "sessions";

  const setTab = (next: AuthTab) => {
    const p = new URLSearchParams(params);
    p.set("tab", next);
    setParams(p, { replace: true });
  };

  return (
    <div className="animate-fade-in-up flex flex-col gap-3.5">
      <TabStrip tabs={TABS} value={tab} onChange={setTab} />

      {tab === "sessions" && <SessionsPanel />}
      {tab === "providers" && <LoginProvidersPanel />}
    </div>
  );
}
