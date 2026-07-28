// Handoff § 7. Authentication (`/app/auth`).
//
// Tabs: Single sign-on · Sessions · API keys · Login providers.
// The active tab is intra-screen SELECTION, so it lives in the URL as `?tab=`
// — not in Zustand (CLAUDE.md › Frontend conventions).

import { useSearchParams } from "react-router-dom";
import { ApiKeysPanel } from "./ApiKeysPanel";
import { LoginProvidersPanel } from "./LoginProvidersPanel";
import { SessionsPanel } from "./SessionsPanel";
import { SsoPanel } from "./SsoPanel";
import { TabStrip } from "./TabStrip";

const TABS = [
  { value: "sso", label: "Single sign-on" },
  { value: "sessions", label: "Sessions" },
  { value: "keys", label: "API keys" },
  { value: "providers", label: "Login providers" },
] as const;

type AuthTab = (typeof TABS)[number]["value"];

const isTab = (value: string | null): value is AuthTab =>
  TABS.some((t) => t.value === value);

export default function AuthScreen() {
  const [params, setParams] = useSearchParams();
  const raw = params.get("tab");
  const tab: AuthTab = isTab(raw) ? raw : "sso";

  const setTab = (next: AuthTab) => {
    const p = new URLSearchParams(params);
    p.set("tab", next);
    setParams(p, { replace: true });
  };

  return (
    <div className="animate-fade-in-up flex flex-col gap-3.5">
      <TabStrip tabs={TABS} value={tab} onChange={setTab} />

      {tab === "sso" && <SsoPanel />}
      {tab === "sessions" && <SessionsPanel />}
      {tab === "keys" && <ApiKeysPanel />}
      {tab === "providers" && <LoginProvidersPanel />}
    </div>
  );
}
