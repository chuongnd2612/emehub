// Handoff § 9. Integrations — the provider-connection manager, wired to
// `GET|POST /connections`, `PATCH|DELETE /connections/{id}` and
// `POST /connections/{id}/test`.
//
// A summary strip, then one block per provider (Azure DevOps, Jira Cloud,
// GitHub) listing its connections. A connection expands into its credential
// form; `Test connection` really calls the provider, so it takes as long as
// the provider takes and can genuinely fail — the row shows the hub's message
// either way.
//
// Intra-screen selection (which connection is open) lives in a query param,
// per CLAUDE.md › "The URL is the source of truth for navigation".

import { useCallback, useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";

import {
  ErrorState,
  GlassCard,
  Icon,
  LoadingState,
  Notice,
  toast,
} from "@/components/ui";
import {
  PROVIDERS,
  createConnection,
  getConnections,
  removeConnection,
  saveConnection,
  testConnection,
  type Connection,
  type ConnectionGroup,
  type ProviderKey,
} from "@/data";
import { ApiError } from "@/lib/api";
import { cn } from "@/lib/cn";
import type { ConnectionTestOutcome } from "./ConnectionRow";
import { ProviderGroup } from "./ProviderGroup";

/** The hub's message when it has one, the exception's otherwise. */
function errorMessage(err: unknown, fallback: string): string {
  if (err instanceof ApiError) return err.message || fallback;
  if (err instanceof Error) return err.message || fallback;
  return fallback;
}

export default function IntegrationsScreen() {
  const [groups, setGroups] = useState<ConnectionGroup[]>([]);
  const [load, setLoad] = useState<"loading" | "ready" | "error">("loading");
  const [loadError, setLoadError] = useState<string | null>(null);
  const [reloadKey, setReloadKey] = useState(0);
  const [testingId, setTestingId] = useState<number | null>(null);
  /**
   * Last test outcome per connection id, for this session.
   *
   * Kept here rather than on the wire row: `GET /connections` reports `status`
   * and `lastTested`, never the reason a test failed — and the reason is the
   * actionable half. A toast alone loses it after 3.2s.
   */
  const [results, setResults] = useState<Record<number, ConnectionTestOutcome>>(
    {},
  );
  const [savingId, setSavingId] = useState<number | null>(null);
  const [addingProvider, setAddingProvider] = useState<ProviderKey | null>(null);
  const [params, setParams] = useSearchParams();

  const expandedId = params.get("conn");

  const reload = useCallback(() => setReloadKey((n) => n + 1), []);

  useEffect(() => {
    let live = true;
    setLoad("loading");
    setLoadError(null);
    getConnections()
      .then((next) => {
        if (!live) return;
        setGroups(next);
        setLoad("ready");
      })
      .catch((err: unknown) => {
        if (!live) return;
        setLoadError(errorMessage(err, "Could not reach the hub"));
        setLoad("error");
      });
    return () => {
      live = false;
    };
  }, [reloadKey]);

  /**
   * Every Azure DevOps organisation this workspace already reaches.
   *
   * Azure DevOps refuses to enumerate organisations for a token scoped to one of
   * them, which is the default kind — but the hub does not need the provider to
   * know which organisations are in use here, because it is already storing
   * them. So the organisation field can be a picker even when discovery cannot
   * answer, and only the first connection into a new organisation has to be
   * typed (#173).
   *
   * Read from the *saved* URLs, never the editable fields: a half-typed
   * organisation is not one this workspace uses.
   */
  const knownOrgUrls = groups
    .filter((g) => g.kind === "azure_devops")
    .flatMap((g) => g.connections.map((c) => c.savedBaseUrl))
    .filter(Boolean);

  const connectionCount = groups.reduce((n, g) => n + g.connections.length, 0);
  const providerCount = groups.filter((g) => g.connections.length > 0).length;
  const verifiedCount = groups.reduce(
    (n, g) => n + g.connections.filter((c) => c.status === "Connected").length,
    0,
  );

  const setExpanded = (connectionId: number) => {
    const next = new URLSearchParams(params);
    if (expandedId === String(connectionId)) next.delete("conn");
    else next.set("conn", String(connectionId));
    setParams(next, { replace: true });
  };

  /** Apply a change to one connection, leaving every other group untouched. */
  const patchConnection = (
    connectionId: number,
    patch: (c: Connection) => Connection,
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
    connectionId: number,
    fieldKey: string,
    value: string,
  ) =>
    patchConnection(connectionId, (c) => ({
      ...c,
      fields: c.fields.map((f) => (f.key === fieldKey ? { ...f, value } : f)),
    }));

  const handleLabelChange = (connectionId: number, value: string) =>
    patchConnection(connectionId, (c) => ({ ...c, label: value }));

  const handleTest = async (connection: Connection) => {
    // One test in flight at a time, as in the prototype.
    if (testingId) return;
    setTestingId(connection.id);
    try {
      const result = await testConnection(connection.id);
      patchConnection(connection.id, (c) => ({
        ...c,
        status: result.ok ? "Connected" : "Attention",
        lastTested: "active now",
      }));
      setResults((r) => ({
        ...r,
        [connection.id]: {
          ok: result.ok,
          message: result.message,
          unreachable: false,
        },
      }));
      if (result.ok) {
        toast("Connection verified");
      } else {
        // The provider's own reason is the actionable half — keep it.
        toast("Connection failed", "warn", result.message);
      }
    } catch (err) {
      // The hub answering with an error is NOT the same as never answering: one
      // means the provider rejected us, the other means we cannot tell. An
      // ApiError is a reply, so anything else is a transport failure.
      const unreachable = !(err instanceof ApiError);
      const message = errorMessage(
        err,
        unreachable
          ? "The hub did not respond, so the connection is untested"
          : `${connection.label} did not respond`,
      );
      setResults((r) => ({
        ...r,
        [connection.id]: { ok: false, message, unreachable },
      }));
      // The status is deliberately NOT patched to "Attention" here: we did not
      // learn anything about the connection, only about the hub.
      toast(
        unreachable ? "EmeHub is unreachable" : "Connection failed",
        "warn",
        message,
      );
    } finally {
      setTestingId(null);
    }
  };

  const handleSave = async (connection: Connection) => {
    setSavingId(connection.id);
    try {
      const saved = await saveConnection(connection);
      patchConnection(connection.id, () => saved);
      toast("Connection saved");
    } catch (err) {
      toast(
        "Could not save the connection",
        "warn",
        errorMessage(err, "The hub rejected the change"),
      );
    } finally {
      setSavingId(null);
    }
  };

  const handleRemove = async (connection: Connection) => {
    try {
      await removeConnection(connection.id);
    } catch (err) {
      toast(
        "Could not remove the connection",
        "warn",
        errorMessage(err, "The hub rejected the change"),
      );
      return;
    }
    setGroups((prev) =>
      prev.map((g) => ({
        ...g,
        connections: g.connections.filter((c) => c.id !== connection.id),
      })),
    );
    if (expandedId === String(connection.id)) {
      const next = new URLSearchParams(params);
      next.delete("conn");
      setParams(next, { replace: true });
    }
    toast(`${connection.label} removed`, "warn");
  };

  /**
   * `+ Add connection` creates the row for real and opens it. The expanded row
   * IS the connection form in this design, so there is no second modal to
   * invent — the new connection exists with no credential until it is saved.
   */
  const handleAdd = async (provider: ProviderKey) => {
    if (addingProvider) return;
    setAddingProvider(provider);
    const name = PROVIDERS[provider].name;
    try {
      const created = await createConnection(provider, `New ${name} connection`);
      setGroups((prev) =>
        prev.map((g) =>
          g.provider === provider
            ? { ...g, connections: [...g.connections, created] }
            : g,
        ),
      );
      const next = new URLSearchParams(params);
      next.set("conn", String(created.id));
      setParams(next, { replace: true });
      toast(`Add ${name} connection`, "info");
    } catch (err) {
      toast(
        `Could not add a ${name} connection`,
        "warn",
        errorMessage(err, "The hub rejected the request"),
      );
    } finally {
      setAddingProvider(null);
    }
  };

  if (load === "loading") {
    return <LoadingState label="Loading provider connections…" />;
  }
  if (load === "error") {
    return (
      <ErrorState
        title="Could not load provider connections"
        detail={loadError ?? undefined}
        onRetry={reload}
      />
    );
  }

  return (
    <div className="animate-fade-in-up flex flex-col gap-[14px]">
      {/* Summary strip */}
      <GlassCard className="flex flex-wrap items-center gap-[14px] px-5 py-4">
        <span
          className={cn(
            "animate-pulse-dot size-2 shrink-0 rounded-full",
            verifiedCount > 0 ? "bg-ok" : "bg-label",
          )}
        />
        <span className="text-[12.5px] font-semibold text-txt3">
          {providerCount} {providerCount === 1 ? "provider" : "providers"} ·{" "}
          {connectionCount}{" "}
          {connectionCount === 1 ? "connection" : "connections"} ·{" "}
          {verifiedCount} verified
        </span>
        <span className="text-[11.5px] text-label">
          Credentials encrypted at rest · tokens never leave EmeHub
        </span>
      </GlassCard>

      {/* The `Import all` control the handoff draws has no endpoint: nothing in
          the API imports across every provider at once. It is omitted rather
          than wired to a toast that pretends. */}
      <Notice tone="info">
        A token you store here can be replaced but never read back — the hub
        returns whether a credential exists, never the credential.
      </Notice>

      {connectionCount === 0 && (
        <Notice tone="warn">
          No provider connections yet. Add one below, then run Test connection
          to prove the credential reaches the provider.
        </Notice>
      )}

      {/* One block per provider */}
      <div className="flex flex-col gap-5">
        {groups.map((g) => (
          <ProviderGroup
            key={g.provider}
            group={g}
            provider={PROVIDERS[g.provider]}
            name={PROVIDERS[g.provider].name}
            expandedId={expandedId}
            testingId={testingId}
            results={results}
            savingId={savingId}
            adding={addingProvider === g.provider}
            onToggle={setExpanded}
            onFieldChange={handleFieldChange}
            onLabelChange={handleLabelChange}
            onTest={handleTest}
            onSave={handleSave}
            onRemove={handleRemove}
            onAdd={() => void handleAdd(g.provider)}
            knownOrgUrls={knownOrgUrls}
          />
        ))}
      </div>
    </div>
  );
}
