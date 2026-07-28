// Handoff § 9. Integrations — the provider-connection manager.
//
// Mirrors Q-Agent's provider settings: a summary strip, then one block per
// provider (Azure DevOps, Jira Cloud, GitHub) listing its connections. A
// connection expands into its credential form; `Test connection` runs for
// ~1300 ms and then marks it Connected / just now.
//
// Data comes from the typed stub layer (`@/data`) — there is no API yet.
// Intra-screen selection (which connection is open) lives in a query param,
// per CLAUDE.md › "The URL is the source of truth for navigation".

import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";

import { GlassCard, Icon, toast } from "@/components/ui";
import {
  PROVIDERS,
  getConnections,
  getIntegrations,
  removeConnection,
  saveConnection,
  testConnection,
  type Integration,
  type ProviderConnection,
  type ProviderConnectionGroup,
} from "@/data";
import { cn } from "@/lib/cn";
import { ProviderGroup } from "./ProviderGroup";

export default function IntegrationsScreen() {
  const [groups, setGroups] = useState<ProviderConnectionGroup[]>([]);
  const [integrations, setIntegrations] = useState<Integration[]>([]);
  const [testingId, setTestingId] = useState<string | null>(null);
  const [params, setParams] = useSearchParams();

  const expandedId = params.get("conn");

  useEffect(() => {
    void getConnections().then(setGroups);
    void getIntegrations().then(setIntegrations);
  }, []);

  const providerCount = groups.length;
  const connectionCount = groups.reduce((n, g) => n + g.connections.length, 0);

  const setExpanded = (connectionId: string) => {
    const next = new URLSearchParams(params);
    if (expandedId === connectionId) next.delete("conn");
    else next.set("conn", connectionId);
    setParams(next, { replace: true });
  };

  /** Apply a change to one connection, leaving every other group untouched. */
  const patchConnection = (
    connectionId: string,
    patch: (c: ProviderConnection) => ProviderConnection,
  ) =>
    setGroups((prev) =>
      prev.map((g) => ({
        ...g,
        connections: g.connections.map((c) =>
          c.id === connectionId ? patch(c) : c,
        ),
      })),
    );

  const handleFieldChange = (
    connectionId: string,
    fieldKey: string,
    value: string,
  ) =>
    patchConnection(connectionId, (c) => ({
      ...c,
      fields: c.fields.map((f) => (f.key === fieldKey ? { ...f, value } : f)),
    }));

  const handleTest = async (connection: ProviderConnection) => {
    // One test in flight at a time, as in the prototype.
    if (testingId) return;
    setTestingId(connection.id);
    const result = await testConnection(connection.id);
    setTestingId(null);
    if (!result.ok) {
      toast("Connection failed", `${connection.label} did not respond`, "warn");
      return;
    }
    patchConnection(connection.id, (c) => ({
      ...c,
      status: "Connected",
      lastSync: "just now",
    }));
    toast(
      "Connection verified",
      `${connection.label} responded in ${result.latencyMs} ms`,
    );
  };

  const handleSave = async (connection: ProviderConnection) => {
    await saveConnection(connection);
    toast(
      "Connection saved",
      `${connection.label} credentials encrypted and stored`,
    );
  };

  const handleRemove = async (connection: ProviderConnection) => {
    await removeConnection(connection.id);
    setGroups((prev) =>
      prev.map((g) => ({
        ...g,
        connections: g.connections.filter((c) => c.id !== connection.id),
      })),
    );
    if (expandedId === connection.id) {
      const next = new URLSearchParams(params);
      next.delete("conn");
      setParams(next, { replace: true });
    }
    toast(
      "Connection removed",
      `${connection.label} is no longer synced`,
      "warn",
    );
  };

  const handleAdd = (name: string) =>
    toast(
      `Add ${name} connection`,
      "Paste an organisation URL and access token to begin",
      "info",
    );

  const handleImportAll = () =>
    toast("Import started", "Pulling work items from every connected provider");

  return (
    <div className="animate-fade-in-up flex flex-col gap-[14px]">
      {/* Summary strip */}
      <GlassCard className="flex flex-wrap items-center gap-[14px] px-5 py-4">
        <span className="animate-pulse-dot size-2 shrink-0 rounded-full bg-ok" />
        <span className="text-[12.5px] font-semibold text-txt3">
          {providerCount} providers · {connectionCount} connections live
        </span>
        <span className="text-[11.5px] text-label">
          Credentials encrypted at rest · tokens never leave EmeHub
        </span>
        <button
          type="button"
          onClick={handleImportAll}
          className={cn(
            "ml-auto inline-flex cursor-pointer items-center gap-2 rounded-button",
            "border border-bd2 bg-card2 px-4 py-[10px] text-[12.5px] font-semibold text-txt3",
            "transition-colors duration-200 hover:bg-bd",
          )}
        >
          <Icon
            name="sync"
            size={14}
            strokeWidth={2.2}
            className="text-ps-text"
          />
          Import all
        </button>
      </GlassCard>

      {/* One block per provider */}
      <div className="flex flex-col gap-5">
        {groups.map((g) => (
          <ProviderGroup
            key={g.provider}
            group={g}
            provider={PROVIDERS[g.provider]}
            name={
              integrations.find((i) => i.id === g.provider)?.name ??
              PROVIDERS[g.provider].name
            }
            expandedId={expandedId}
            testingId={testingId}
            onToggle={setExpanded}
            onFieldChange={handleFieldChange}
            onTest={handleTest}
            onSave={handleSave}
            onRemove={handleRemove}
            onAdd={() => handleAdd(PROVIDERS[g.provider].name)}
          />
        ))}
      </div>
    </div>
  );
}
