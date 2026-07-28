// Handoff › 6. Claude Settings — "Tabs: Credentials · Models · Agent
// preferences, with a right-aligned `Save changes` primary."
//
// Renders inside the app shell's scroll region: the page root is
// `display:flex; flex-direction:column; gap:14px` + `fadeInUp .38s ease both`.
//
// The active tab lives in the URL (`?tab=`) — intra-screen selection goes in a
// query param, never in the store (CLAUDE.md › Routing & navigation).

import { useSearchParams } from "react-router-dom";
import { Button, toast } from "@/components/ui";
import { cn } from "@/lib/cn";
import { AgentPreferencesTab } from "./AgentPreferencesTab";
import { CredentialsTab } from "./CredentialsTab";
import { ModelsTab } from "./ModelsTab";
import { useClaudeSettings } from "./state";

const TABS = [
  { key: "credentials", label: "Credentials" },
  { key: "models", label: "Models" },
  { key: "agents", label: "Agent preferences" },
] as const;

type TabKey = (typeof TABS)[number]["key"];

function isTabKey(value: string | null): value is TabKey {
  return TABS.some((t) => t.key === value);
}

export default function ClaudeScreen() {
  const [params, setParams] = useSearchParams();
  const raw = params.get("tab");
  const tab: TabKey = isTabKey(raw) ? raw : "credentials";

  const settings = useClaudeSettings();

  const selectTab = (next: TabKey) => {
    const nextParams = new URLSearchParams(params);
    nextParams.set("tab", next);
    setParams(nextParams, { replace: true });
  };

  return (
    <div className="flex animate-fade-in-up flex-col gap-[14px]">
      <div className="flex flex-wrap items-center gap-2">
        {TABS.map((t) => {
          const active = t.key === tab;
          return (
            <button
              key={t.key}
              type="button"
              role="tab"
              aria-selected={active}
              data-surface
              onClick={() => selectTab(t.key)}
              className={cn(
                "cursor-pointer rounded-control-lg border px-4 py-[9px] text-[12.5px] font-bold",
                active
                  ? "border-pb bg-pt text-p-on"
                  : "border-transparent bg-transparent text-muted hover:bg-card3 hover:text-txt3",
              )}
            >
              {t.label}
            </button>
          );
        })}

        <Button
          variant="primary"
          className="ml-auto h-auto px-5 py-[11px] text-[13px]"
          onClick={() =>
            toast(
              "Settings saved",
              "Credentials and model defaults applied to both agents",
              "ok",
            )
          }
        >
          Save changes
        </Button>
      </div>

      {tab === "credentials" && <CredentialsTab s={settings} />}
      {tab === "models" && <ModelsTab s={settings} />}
      {tab === "agents" && <AgentPreferencesTab s={settings} />}
    </div>
  );
}
