// Tickets — the synced work-item mirror, its filter schema, and importing.
//
//   GET    /tickets            getTicketPage / getTickets
//   GET    /tickets/{id}       getTicket
//   DELETE /tickets/{id}       deleteTicket
//   POST   /tickets/sync       runImport
//
// ## Filtering moved to the server
//
// The handoff's rule — "provider match && every set field equals the ticket's
// field && query matches id|title|project" — is now `GET /tickets`' own
// behaviour, so nothing is filtered in the browser. Each pill maps to one query
// parameter (`FIELD_SPECS`), and the response is one page of a server-side
// paginated set.
//
// ## The provider vocabulary
//
// `POST /tickets/sync` stamps each row with the *connection's* kind, so both
// the `providerKind` filter and the sync body speak `azure_devops | jira |
// github` (see `PROVIDER_WIRE_KIND` in `data/projects.ts`).
//
// ## Filter options come from the store, not from a fixture
//
// The field LIST is static and local — it is provider vocabulary, not data
// (Azure has an area path, Jira has an epic). The OPTIONS are not: the
// prototype's "Sprint 24" / `Surveyor\QA` were invented. They are derived from
// the distinct values actually present in the hub's store for the active
// provider, so every pill offers a value that can return a row, and an empty
// store shows no pills at all.
//
// Two GitHub pills from the handoff are gone: `GET /tickets` has no `milestone`
// or `label` parameter, and a pill that changes nothing is a lying control.

import { api } from "@/lib/api";
import type { TicketQuery as ClauseQuery } from "./ticketQuery";
import { relativeTime } from "./humanize";
import {
  PROVIDER_DISPLAY,
  PROVIDER_WIRE_KIND,
  providerFromKind,
} from "./projects";
import type {
  ImportRequest,
  ImportResult,
  ProviderKey,
  Ticket,
  TicketFilterField,
  TicketFilters,
  TicketFilterSchema,
  TicketPage,
} from "./types";

/* ── Wire shapes ─────────────────────────────────────────────────────────── */

interface TicketWire {
  id: number;
  externalId: string;
  providerKind?: string;
  projectId?: number | null;
  connectionId?: number | null;
  title?: string;
  workItemType?: string;
  status?: string;
  priority?: string;
  assignee?: string;
  sprint?: string;
  areaPath?: string;
  epic?: string;
  labels?: unknown[];
  acCount?: number;
  syncedAt?: string | null;
}

interface TicketPageWire {
  items?: TicketWire[];
  total?: number;
  page?: number;
  pageSize?: number;
}

/** The hub's cap on `pageSize`. The table has no pager, so ask for the lot. */
export const MAX_PAGE_SIZE = 200;

const toTicket = (
  wire: TicketWire,
  projectNameById: Map<number, string>,
): Ticket => ({
  id: wire.externalId,
  title: wire.title ?? "",
  provider: providerFromKind(wire.providerKind ?? ""),
  status: wire.status ?? "",
  type: wire.workItemType ?? "",
  priority: wire.priority ?? "",
  project: wire.projectId ? (projectNameById.get(wire.projectId) ?? "") : "",
  owner: wire.assignee ?? "",
  sprint: wire.sprint ?? "",
  area: wire.areaPath ?? "",
  epic: wire.epic ?? "",
  labels: (wire.labels ?? []).filter((l): l is string => typeof l === "string"),
  acCount: wire.acCount ?? 0,
  synced: relativeTime(wire.syncedAt ?? null),
  syncedAt: wire.syncedAt ?? null,
});

/* ── The filter schema ───────────────────────────────────────────────────── */

/** A pill: where its value lives on a ticket, and which param it drives. */
interface FieldSpec {
  key: string;
  label: string;
  /** `GET /tickets` query parameter. */
  param: string;
  /** Reads the field off a ticket, for deriving the option list. */
  read: (ticket: Ticket) => string;
}

/**
 * Handoff § 4 — the provider-variant filter set, minus every field the hub
 * cannot filter on. Static and local: this is vocabulary, not data.
 */
const FIELD_SPECS: Record<ProviderKey, FieldSpec[]> = {
  ado: [
    { key: "sprint", label: "Sprint", param: "sprint", read: (t) => t.sprint },
    { key: "area", label: "Area path", param: "areaPath", read: (t) => t.area },
    { key: "status", label: "State", param: "status", read: (t) => t.status },
    {
      key: "type",
      label: "Work item type",
      param: "workItemTypes",
      read: (t) => t.type,
    },
  ],
  jira: [
    { key: "sprint", label: "Sprint", param: "sprint", read: (t) => t.sprint },
    { key: "epic", label: "Epic", param: "epic", read: (t) => t.epic },
    { key: "status", label: "Status", param: "status", read: (t) => t.status },
    {
      key: "type",
      label: "Issue type",
      param: "workItemTypes",
      read: (t) => t.type,
    },
    {
      key: "priority",
      label: "Priority",
      param: "priority",
      read: (t) => t.priority,
    },
  ],
  gh: [
    { key: "status", label: "State", param: "status", read: (t) => t.status },
    {
      key: "type",
      label: "Issue type",
      param: "workItemTypes",
      read: (t) => t.type,
    },
    { key: "owner", label: "Assignee", param: "assignee", read: (t) => t.owner },
  ],
};

const PARAM_BY_KEY = new Map<string, string>(
  Object.values(FIELD_SPECS)
    .flat()
    .map((spec) => [spec.key, spec.param]),
);

/**
 * The filter set for one provider, with options taken from `rows`.
 *
 * Pass the UNFILTERED page for the active provider — deriving the options from
 * an already-filtered set would collapse every pill to the value just chosen.
 */
export const buildTicketFilterSchema = (
  provider: ProviderKey,
  rows: Ticket[],
): TicketFilterField[] =>
  FIELD_SPECS[provider]
    .map((spec) => ({
      key: spec.key,
      label: spec.label,
      param: spec.param,
      options: [...new Set(rows.map(spec.read).filter(Boolean))].sort((a, b) =>
        a.localeCompare(b),
      ),
    }))
    // A pill with nothing to offer is noise.
    .filter((field) => field.options.length > 0);

/**
 * STUB (correctly static and local): the whole schema, keyed by provider.
 *
 * There is no `/tickets/schema` endpoint and there should not be one — the
 * field list is UI vocabulary. The OPTIONS are real, so this takes the rows for
 * whichever providers the caller has loaded.
 */
export const getTicketFilterSchema = async (
  rowsByProvider: Partial<Record<ProviderKey, Ticket[]>> = {},
): Promise<TicketFilterSchema> => ({
  ado: buildTicketFilterSchema("ado", rowsByProvider.ado ?? []),
  jira: buildTicketFilterSchema("jira", rowsByProvider.jira ?? []),
  gh: buildTicketFilterSchema("gh", rowsByProvider.gh ?? []),
});

/* ── Reads ───────────────────────────────────────────────────────────────── */

/** Project row id → display name, so the PROJECT column can show one. */
const projectNameMap = async (): Promise<Map<number, string>> => {
  try {
    const rows = await api.get<{ id: number; key: string; name?: string }[]>(
      "/projects",
    );
    return new Map(rows.map((r) => [r.id, r.name?.trim() || r.key]));
  } catch {
    // The column degrades to blank rather than failing the whole table.
    return new Map();
  }
};

export interface TicketQuery {
  provider?: ProviderKey | null;
  filters?: TicketFilters;
  query?: string;
  page?: number;
  pageSize?: number;
  /** Restrict to one registry row (`ProjectOut.id`, not the key). */
  projectId?: number;
}

const toQueryParams = ({
  provider,
  filters = {},
  query = "",
  page = 1,
  pageSize = MAX_PAGE_SIZE,
  projectId,
}: TicketQuery): Record<string, string | number | undefined> => {
  const params: Record<string, string | number | undefined> = {
    providerKind: provider ? PROVIDER_WIRE_KIND[provider] : undefined,
    projectId,
    q: query.trim() || undefined,
    page,
    pageSize,
  };
  for (const [key, value] of Object.entries(filters)) {
    if (!value) continue;
    const param = PARAM_BY_KEY.get(key);
    if (param) params[param] = value;
  }
  return params;
};

/**
 * `GET /tickets` for a **count only** — `total`, nothing decoded.
 *
 * `getTicketPage` also fetches `/projects` to label the PROJECT column; a
 * caller that only wants the number (the sidebar badge) should not pay for
 * that second request.
 */
export const countTickets = async (
  options: TicketQuery = {},
): Promise<number> => {
  const wire = await api.get<TicketPageWire>("/tickets", {
    query: toQueryParams({ ...options, pageSize: 1 }),
  });
  return wire.total ?? 0;
};

/** GET /tickets — one page, filtered and paged by the hub. */
export const getTicketPage = async (
  options: TicketQuery = {},
): Promise<TicketPage> => {
  const [wire, projects] = await Promise.all([
    api.get<TicketPageWire>("/tickets", { query: toQueryParams(options) }),
    projectNameMap(),
  ]);
  return {
    items: (wire.items ?? []).map((row) => toTicket(row, projects)),
    total: wire.total ?? 0,
    page: wire.page ?? 1,
    pageSize: wire.pageSize ?? MAX_PAGE_SIZE,
  };
};

/**
 * The rows only. Kept positional for the command palette, which asks for one
 * provider at a time and wants nothing else.
 */
export const getTickets = async (
  provider: ProviderKey,
  filters: TicketFilters = {},
  query = "",
): Promise<Ticket[]> =>
  (await getTicketPage({ provider, filters, query })).items;

/** GET /tickets/{externalId}. */
export const getTicket = async (
  externalId: string,
  provider?: ProviderKey,
): Promise<Ticket> => {
  const [wire, projects] = await Promise.all([
    api.get<TicketWire>(`/tickets/${encodeURIComponent(externalId)}`, {
      query: provider
        ? { providerKind: PROVIDER_WIRE_KIND[provider] }
        : undefined,
    }),
    projectNameMap(),
  ]);
  return toTicket(wire, projects);
};

/** DELETE /tickets/{externalId}. Local only — a re-sync restores the row. */
export const deleteTicket = (externalId: string): Promise<unknown> =>
  api.delete(`/tickets/${encodeURIComponent(externalId)}`);

/* ── Import ──────────────────────────────────────────────────────────────── */

/**
 * Handoff § 5 → `POST /tickets/sync`.
 *
 * `mode` is the adapter's selection strategy: `sprint` (the named sprint),
 * `assigned` (the authenticated identity's items), or anything else, which
 * means "everything matching the filters". Advanced mode therefore sends `all`
 * plus the field filters.
 *
 * **This 404s when no work-item connection of that kind exists** — the correct
 * answer for a workspace that has not wired a provider yet, not a bug. The
 * caller surfaces the hub's own message; see `components/import/useImportRun`.
 */
export const runImport = async (
  request: ImportRequest,
): Promise<ImportResult> => {
  const filters = request.filters ?? {};
  const advanced = request.mode === "advanced";

  const result = await api.post<{ synced?: number }>("/tickets/sync", {
    providerKind: PROVIDER_WIRE_KIND[request.provider],
    mode: advanced ? "all" : request.scope,
    // A clause query wins server-side and the legacy fields below are ignored.
    // They are still sent because this route is a contract agents call and the
    // legacy path is the bridge — see SyncRequest.
    query: request.query ?? undefined,
    sprint: filters.sprint || undefined,
    areaPath: filters.area || undefined,
    states: filters.status ? [filters.status] : [],
    workItemTypes: filters.type ? [filters.type] : [],
  });

  return {
    count: result.synced ?? 0,
    provider: PROVIDER_DISPLAY[request.provider],
    scopeLabel: request.query
      ? "your query"
      : advanced
      ? "field filters applied"
      : {
          sprint: "active sprint",
          assigned: "items assigned to you",
          all: "all open items",
        }[request.scope],
  };
};


/* ── The query builder's preview ─────────────────────────────────────────── */

export interface QueryPreview {
  /** How many work items the provider matched. */
  total: number;
  /** A short sample — enough to confirm the shape, not to read the result. */
  sample: Ticket[];
  /** The query in words. */
  description: string;
}

/**
 * `POST /tickets/query/preview` — what a query *would* import, without importing.
 *
 * The hub makes the provider call with its own stored PAT, exactly as the sync
 * does. Nothing is written, so this is safe to run on every Apply — and it is what
 * finally makes an honest item count possible before a pull.
 *
 * A 422 carries `{problems: [{message, clauseIndex}]}` from the same validator the
 * client greys out Apply with, so reaching it usually means the two have drifted.
 */
export const previewTicketQuery = async (options: {
  provider: ProviderKey;
  query: ClauseQuery;
  connectionId?: number;
  project?: string;
}): Promise<QueryPreview> => {
  const wire = await api.post<{
    total?: number;
    sample?: TicketWire[];
    description?: string;
  }>("/tickets/query/preview", {
    providerKind: PROVIDER_WIRE_KIND[options.provider],
    connectionId: options.connectionId,
    project: options.project,
    query: options.query,
  });
  const projects = await projectNameMap();
  return {
    total: wire.total ?? 0,
    sample: (wire.sample ?? []).map((row) => toTicket(row, projects)),
    description: wire.description ?? "",
  };
};
