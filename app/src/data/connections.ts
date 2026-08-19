// Provider connections — real calls to the hub.
//
// Endpoint map:
//   GET    /connections                 getConnections / getIntegrations
//   POST   /connections                 createConnection
//   PATCH  /connections/{id}            saveConnection
//   DELETE /connections/{id}            removeConnection
//   POST   /connections/{id}/test       testConnection
//
// ## The PAT never comes back
//
// `ConnectionOut` has no PAT field and never will (CLAUDE.md › Security rules;
// `api/app/routers/connections.py`). All the wire says is `hasPat`. So the
// credential input in the Integrations form is always empty on load: a stored
// token may be *replaced*, never read. `saveConnection` sends `pat` only when
// the user typed one — an omitted `pat` keeps the stored credential, which is
// what lets a label be edited without re-typing the token.
//
// The hub's kinds are spelled out (`azure_devops` | `github` | `jira`); the
// design system's provider keys are the two-letter `ado` | `gh` | `jira`. The
// translation lives here and nowhere else.

import { api } from "@/lib/api";
import { PROVIDERS, PROVIDER_ORDER } from "./fixtures/providers";
import { relativeTime } from "./humanize";
import type {
  ConnectionFieldType,
  ConnectionStatus,
  Integration,
  ProviderKey,
} from "./types";

export { PROVIDERS };

/* ── Wire types ──────────────────────────────────────────────────────────── */

/** The hub's provider kinds. */
export type ConnectionKind = "azure_devops" | "github" | "jira";

/** `ConnectionOut`. Note the absence of anything credential-shaped. */
export interface ConnectionWire {
  id: number;
  kind: string;
  label: string;
  baseUrl: string;
  config: Record<string, unknown>;
  capabilities: string[];
  supportedCapabilities: string[];
  /** Whether a credential is stored. Never the credential. */
  hasPat: boolean;
  connected: boolean;
  shared: boolean;
  lastSync: string | null;
  lastTestedAt: string | null;
  createdAt: string | null;
  updatedAt: string | null;
}

/** `POST /connections/{id}/test` — a real provider round-trip, so it can fail. */
export interface ConnectionTestOutcome {
  ok: boolean;
  message: string;
  detail: Record<string, unknown>;
  latencyMs: number;
}

/* ── Screen types ────────────────────────────────────────────────────────── */

/** One editable field of a connection form. */
export interface ConnectionFormField {
  /** `baseUrl`, or a key inside `config`. */
  key: string;
  label: string;
  value: string;
  type: ConnectionFieldType;
  /** Shown when the field is empty. */
  placeholder?: string;
  /** True for the credential field — its value is never loaded from the hub. */
  secret?: boolean;
}

/** A connection as the Integrations screen renders it. */
export interface Connection {
  id: number;
  kind: ConnectionKind;
  provider: ProviderKey;
  label: string;
  /** Mono one-liner, e.g. `dev.azure.com/emesoft · Surveyor`. */
  summary: string;
  status: ConnectionStatus;
  /** "2 min ago" / "never". */
  lastTested: string;
  hasPat: boolean;
  shared: boolean;
  capabilities: string[];
  fields: ConnectionFormField[];
  /**
   * The base URL **as stored**, unlike the editable copy in `fields`.
   *
   * The two diverge the moment someone edits the field, and a provider read runs
   * against the stored connection — so a picker that lists an organisation's
   * projects has to key on this, or it will confidently show one organisation's
   * projects under another's name (every entry plausible, all of them wrong).
   */
  savedBaseUrl: string;
}

export interface ConnectionGroup {
  provider: ProviderKey;
  kind: ConnectionKind;
  /** What the connections in this group supply, e.g. "work items · repositories". */
  capabilitiesLabel: string;
  connections: Connection[];
}

/* ── Kind <-> provider key ───────────────────────────────────────────────── */

const KIND_BY_PROVIDER: Record<ProviderKey, ConnectionKind> = {
  ado: "azure_devops",
  gh: "github",
  jira: "jira",
};

const PROVIDER_BY_KIND: Record<string, ProviderKey> = {
  azure_devops: "ado",
  github: "gh",
  jira: "jira",
};

export const kindForProvider = (provider: ProviderKey): ConnectionKind =>
  KIND_BY_PROVIDER[provider];

const CAPABILITY_LABEL: Record<string, string> = {
  work_item: "work items",
  repository: "repositories",
};

const capabilitiesLabel = (capabilities: string[]): string =>
  capabilities.length === 0
    ? "no capabilities"
    : capabilities.map((c) => CAPABILITY_LABEL[c] ?? c).join(" · ");

/* ── Field schemas ───────────────────────────────────────────────────────── */

const str = (value: unknown): string =>
  typeof value === "string" ? value : value == null ? "" : String(value);

/**
 * The fields each kind's adapter actually reads
 * (`api/app/services/adapters/*.py`) plus the one credential field.
 *
 * This is narrower than the handoff's list because the handoff was drawn
 * against a different backend: there is no ADO "Area path" on a connection
 * (area paths are a sync filter, not adapter config) and GitHub authenticates
 * with a PAT, not a GitHub App, so there is no installation id or private key.
 */
function fieldsFor(kind: ConnectionKind, wire: ConnectionWire): ConnectionFormField[] {
  const cfg = wire.config ?? {};
  const secret = (label: string): ConnectionFormField => ({
    key: "pat",
    label,
    value: "",
    type: "password",
    secret: true,
    placeholder: wire.hasPat
      ? "Stored — type a new one to replace it"
      : "Required to reach the provider",
  });

  if (kind === "azure_devops") {
    return [
      {
        key: "baseUrl",
        label: "Organisation URL",
        value: wire.baseUrl,
        type: "text",
        placeholder: "https://dev.azure.com/your-org",
      },
      {
        key: "config.project",
        label: "Project",
        value: str(cfg.project),
        type: "text",
      },
      secret("Personal access token"),
    ];
  }

  if (kind === "jira") {
    return [
      {
        key: "baseUrl",
        label: "Site URL",
        value: wire.baseUrl,
        type: "text",
        placeholder: "https://your-team.atlassian.net",
      },
      {
        key: "config.email",
        label: "Account email",
        value: str(cfg.email),
        type: "text",
      },
      {
        key: "config.project",
        label: "Project key",
        value: str(cfg.project),
        type: "text",
      },
      secret("API token"),
    ];
  }

  return [
    {
      key: "config.org",
      label: "Organisation",
      value: str(cfg.org),
      type: "text",
    },
    {
      key: "config.repo",
      label: "Repository",
      value: str(cfg.repo),
      type: "text",
      placeholder: "Optional — narrows the connection to one repo",
    },
    {
      key: "baseUrl",
      label: "API base URL",
      value: wire.baseUrl,
      type: "text",
      placeholder: "Empty for github.com",
    },
    secret("Personal access token"),
  ];
}

/** The mono sub-line: whatever identifies this account at the provider. */
function summaryFor(kind: ConnectionKind, wire: ConnectionWire): string {
  const cfg = wire.config ?? {};
  const host = wire.baseUrl.replace(/^https?:\/\//, "").replace(/\/+$/, "");
  if (kind === "github") {
    const path = [str(cfg.org), str(cfg.repo)].filter(Boolean).join("/");
    return [host || "github.com", path].filter(Boolean).join(" · ");
  }
  return [host, str(cfg.project)].filter(Boolean).join(" · ") || "not configured";
}

/**
 * `connected` is the last test verdict, so a never-tested connection is not
 * "Disconnected" — it is unproven. A stored PAT that has never passed a test
 * reads as Attention; no PAT at all is Disconnected.
 */
function statusFor(wire: ConnectionWire): ConnectionStatus {
  if (wire.connected) return "Connected";
  return wire.hasPat ? "Attention" : "Disconnected";
}

function toConnection(wire: ConnectionWire): Connection {
  const provider = PROVIDER_BY_KIND[wire.kind] ?? "ado";
  const kind = (KIND_BY_PROVIDER[provider] ?? "azure_devops") as ConnectionKind;
  return {
    id: wire.id,
    kind,
    provider,
    label: wire.label || PROVIDERS[provider].name,
    summary: summaryFor(kind, wire),
    status: statusFor(wire),
    lastTested: relativeTime(wire.lastTestedAt),
    hasPat: wire.hasPat,
    shared: wire.shared,
    capabilities: wire.capabilities ?? [],
    fields: fieldsFor(kind, wire),
    savedBaseUrl: wire.baseUrl ?? "",
  };
}

/* ── Reads ───────────────────────────────────────────────────────────────── */

/** `GET /connections`, grouped into the handoff's provider blocks. */
export const getConnections = async (): Promise<ConnectionGroup[]> => {
  const rows = await api.get<ConnectionWire[]>("/connections");
  const byProvider = rows.map(toConnection);
  return PROVIDER_ORDER.map((provider) => {
    const connections = byProvider.filter((c) => c.provider === provider);
    const capabilities = [...new Set(connections.flatMap((c) => c.capabilities))];
    return {
      provider,
      kind: KIND_BY_PROVIDER[provider],
      capabilitiesLabel: capabilitiesLabel(capabilities),
      connections,
    };
  });
};

/**
 * `GET /connections` flattened and filtered to one capability — the shape a
 * project-config picker wants (Q-Agent's "Work Item Provider" / "Repository
 * Provider" dropdowns, `ProjectSettingsForm.tsx`). `"<Provider name> ·
 * <connection label>"` matches Q-Agent's option label exactly.
 */
export const getConnectionsWithCapability = async (
  capability: "work_item" | "repository",
): Promise<{ id: number; label: string; provider: ProviderKey }[]> => {
  const groups = await getConnections();
  return groups.flatMap((g) =>
    g.connections
      .filter((c) => c.capabilities.includes(capability))
      .map((c) => ({
        id: c.id,
        label: `${PROVIDERS[g.provider].name} · ${c.label}`,
        // Carried so a caller can pick the connection for a given provider —
        // the label reads well but is not something to match on.
        provider: g.provider,
      })),
  );
};

/** One organisation as `GET /connections/{id}/organizations` reports it. */
export interface ProviderOrganization {
  name: string;
  /** The provider's own address for the account — stored verbatim as baseUrl. */
  url: string;
}

/**
 * `GET /connections/{id}/organizations` — the only provider read that works on a
 * connection holding **just a credential**, which is what lets the form ask for
 * the token first and then offer a picker (#166).
 *
 * Three outcomes, and the UI has to keep them apart:
 *
 *   supported: false   this provider cannot enumerate accounts — offer the text
 *                      field, and say nothing alarming; nothing is wrong
 *   error: "…"         the call failed and this sentence is the actionable part
 *                      (typically a PAT without the `vso.profile` scope, which
 *                      is a working credential that cannot do this one thing)
 *   organizations: []  it worked, and this credential genuinely sees none
 */
export interface OrganizationsResult {
  provider: string;
  supported: boolean;
  organizations: ProviderOrganization[];
  error: string;
}

export const getConnectionOrganizations = (
  connectionId: number,
): Promise<OrganizationsResult> =>
  api.get<OrganizationsResult>(`/connections/${connectionId}/organizations`);

/** One project as `GET /connections/{id}/projects` reports it. */
export interface DiscoveredProject {
  externalId: string;
  name: string;
  state: string;
}

/**
 * `GET /connections/{id}/projects` — the work-item connection's picker list,
 * the discovery half of Q-Agent's `POST /projects/refresh`. The hub's
 * `Project` row is deliberately a bare registry entry (no `provider_kind` /
 * `external_id` — see `api/app/models/project.py`), so there is no bulk
 * upsert-by-external-id to port; this is the read a "New project" flow uses
 * to let someone pick a REAL project name instead of typing an arbitrary key.
 */
export const discoverConnectionProjects = (
  connectionId: number,
): Promise<DiscoveredProject[]> =>
  api.get<DiscoveredProject[]>(`/connections/${connectionId}/projects`);

/** One repo as `GET /connections/{id}/repos` reports it. */
export interface DiscoveredRepo {
  name: string;
  cloneUrl: string;
  webUrl: string;
  defaultBranch: string;
}

/**
 * `GET /connections/{id}/repos` — the `{provider, repos, error}` wrapper the
 * backend returns so a picker can say *why* it's empty rather than rendering
 * a blank list (`api/app/routers/connections.py::list_repos`).
 */
export const discoverConnectionRepos = (
  connectionId: number,
): Promise<{ provider: string; repos: DiscoveredRepo[]; error: string }> =>
  api.get(`/connections/${connectionId}/repos`);

/**
 * The Overview page's per-provider summary cards, derived from the same
 * `GET /connections` response — the hub has no separate integrations resource.
 *
 * Only providers with at least one connection appear, and every string is
 * something the wire actually says: there is no sync schedule and no work-item
 * count on a connection, so those cells report what is known instead.
 */
export const getIntegrations = async (): Promise<Integration[]> => {
  const groups = await getConnections();
  return groups
    .filter((g) => g.connections.length > 0)
    .map((g) => {
      const provider = PROVIDERS[g.provider];
      const connected = g.connections.filter((c) => c.status === "Connected");
      const withPat = g.connections.filter((c) => c.hasPat);
      const tested = g.connections
        .map((c) => c.lastTested)
        .filter((t) => t !== "never");
      const n = g.connections.length;
      return {
        id: g.provider,
        name: provider.name,
        state: connected.length === n ? "Connected" : ("Attention" as ConnectionStatus),
        meta: `${n} ${n === 1 ? "connection" : "connections"} · ${g.capabilitiesLabel}`,
        auth: `${withPat.length} of ${n} with a stored token`,
        sync: "On demand",
        last: tested[0] ?? "never tested",
        items: `${connected.length} verified`,
      };
    });
};

/* ── Writes ──────────────────────────────────────────────────────────────── */

/** Split the flat form values back into `baseUrl` + `config` + `pat`. */
function toPayload(fields: ConnectionFormField[]): {
  baseUrl?: string;
  config: Record<string, string>;
  pat?: string;
} {
  const config: Record<string, string> = {};
  let baseUrl: string | undefined;
  let pat: string | undefined;
  for (const field of fields) {
    if (field.key === "pat") {
      // Empty means "leave the stored credential alone" — the hub treats an
      // omitted `pat` as keep, and `""` as clear.
      if (field.value) pat = field.value;
      continue;
    }
    if (field.key === "baseUrl") {
      baseUrl = field.value;
      continue;
    }
    if (field.key.startsWith("config.")) config[field.key.slice(7)] = field.value;
  }
  return { baseUrl, config, pat };
}

/** `POST /connections` — a new, empty connection of `kind`, ready to fill in. */
export const createConnection = async (
  provider: ProviderKey,
  label: string,
): Promise<Connection> => {
  const wire = await api.post<ConnectionWire>("/connections", {
    kind: KIND_BY_PROVIDER[provider],
    label,
  });
  return toConnection(wire);
};

/** `PATCH /connections/{id}`. Sends `pat` only when the user typed a new one. */
export const saveConnection = async (
  connection: Connection,
): Promise<Connection> => {
  const { baseUrl, config, pat } = toPayload(connection.fields);
  const body: Record<string, unknown> = { label: connection.label, config };
  if (baseUrl !== undefined) body.baseUrl = baseUrl;
  if (pat !== undefined) body.pat = pat;
  const wire = await api.patch<ConnectionWire>(
    `/connections/${connection.id}`,
    body,
  );
  return toConnection(wire);
};

/**
 * `POST /connections/{id}/test` — really calls the provider, so it is as slow
 * as the provider is and can genuinely fail. `ok: false` carries the reason.
 */
export const testConnection = (
  connectionId: number,
): Promise<ConnectionTestOutcome> =>
  api.post<ConnectionTestOutcome>(`/connections/${connectionId}/test`);

/** `DELETE /connections/{id}` — takes the stored credential with it. */
export const removeConnection = async (connectionId: number): Promise<void> => {
  await api.delete(`/connections/${connectionId}`);
};

/* ── Provider metadata: the query builder's pickers ──────────────────────── */

/** One node of the area or iteration tree, flattened pre-order with its depth. */
export interface ClassificationNode {
  id: string;
  name: string;
  /** The full path a clause uses, e.g. `Surency\Data`. */
  path: string;
  /** 0 for the project root — what a picker indents by. */
  depth: number;
}

/**
 * A work item type with **its own** states.
 *
 * Grouped per type because a Bug and a User Story do not share a state set:
 * offering `Committed` on a Bug builds a query matching nothing, which reads as
 * "there is no work" rather than as the mistake it is.
 */
export interface WorkItemType {
  name: string;
  states: string[];
}

export interface ProviderMember {
  displayName: string;
  /** The account a query matches on, e.g. `duna@emesoft.net`. */
  uniqueName: string;
}

export interface WorkItemMetadata {
  areaPaths: ClassificationNode[];
  iterationPaths: ClassificationNode[];
  workItemTypes: WorkItemType[];
  /** Every state across every type, for a picker not narrowed by type. */
  states: string[];
  members: ProviderMember[];
  tags: string[];
  epics: { key: string; name: string }[];
  /** When the provider was really read; null when it never has been. */
  fetchedAt: string | null;
  /**
   * The cache TTL passed and the refresh failed. The payload is the last good
   * one, **not** an empty shell — so the panel stays usable and prints the cause.
   */
  stale: boolean;
  message: string;
}

const EMPTY_METADATA: WorkItemMetadata = {
  areaPaths: [],
  iterationPaths: [],
  workItemTypes: [],
  states: [],
  members: [],
  tags: [],
  epics: [],
  fetchedAt: null,
  stale: false,
  message: "",
};

/**
 * `GET /connections/{id}/work-item-metadata` — everything the pickers offer.
 *
 * Cached hub-side per connection, because each read spends the PAT against the
 * provider. `refresh` forces a fresh read; a refresh that fails still returns the
 * last good payload with `stale: true`.
 *
 * Hub-audience only: it spends the PAT, so an agent token cannot reach it
 * (INTEGRATION.md §4).
 */
export const getWorkItemMetadata = async (
  connectionId: number,
  options: { refresh?: boolean } = {},
): Promise<WorkItemMetadata> => {
  const wire = await api.get<Partial<WorkItemMetadata>>(
    `/connections/${connectionId}/work-item-metadata`,
    { query: options.refresh ? { refresh: true } : {} },
  );
  return { ...EMPTY_METADATA, ...wire };
};

/** `DELETE /connections/{id}/metadata/cache` — for a payload that is wrong
 * rather than merely old, after the project was reconfigured provider-side. */
export const clearMetadataCache = async (connectionId: number): Promise<void> => {
  await api.delete(`/connections/${connectionId}/metadata/cache`);
};

/** `GET /connections/{id}/sprints` — iterations, newest first as the provider lists them. */
export interface ProviderSprint {
  id: string;
  name: string;
  /** Pass back as `sprint_path` when syncing. */
  path: string;
  startDate: string | null;
  finishDate: string | null;
  state: string | null;
}

export const getSprints = (connectionId: number): Promise<ProviderSprint[]> =>
  api.get<ProviderSprint[]>(`/connections/${connectionId}/sprints`);
