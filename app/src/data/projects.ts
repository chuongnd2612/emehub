// Projects — the project registry, live against the hub.
//
//   GET    /projects                 getProjects
//   POST   /projects                 createProject
//   GET    /projects/{key}           getProject
//   PATCH  /projects/{key}           renameProject
//   GET    /projects/{key}/config    getProjectConfig  (folded into getProject)
//   PUT    /projects/{key}/config    saveProjectConfig
//
// `saveProjectConfig` is the functional core of Q-Agent's "Project Settings"
// screen (`ProjectSettingsForm.tsx`) ported to the hub: the work-item and
// repository provider bindings, base URL, repositories, environments and test
// accounts all live on this one row and all save together — nothing here
// autosaves, matching Q-Agent's "nothing persists until Save" behaviour.
// `ApiModel` on the backend accepts and returns camelCase (`alias_generator=
// to_camel`), so the patch is sent exactly as typed — no snake_case step.
//
// ## A card is a join, not a row
//
// `ProjectOut` is deliberately thin — `{id, key, name, shared, createdAt,
// updatedAt}` and nothing else, because a list response is the easiest thing to
// log wholesale (`api/app/routers/projects.py`). Everything else the handoff's
// card shows lives on two other reads:
//
//   • repo + branch + connections  → GET /projects/{key}/config
//   • framework, confidence, version, last indexed, stack, page objects
//                                  → GET /projects/{key}/knowledge  (`data/knowledge.ts`)
//   • work items mirrored          → GET /tickets?projectId=…
//
// So `getProjects()` is `1 + 3N` requests, fanned out with `Promise.all`. That
// is the shape the API gives us; an `?expand=` parameter would be an API
// change, not a client one.
//
// ## What has no source, and stays absent
//
// `tests`, `coverage`, `runs` and `passRate` from the handoff's card are
// QAgent's run history. The hub does no domain work (ADR 0001) and stores no
// runs, so those fields are gone from `Project` rather than filled with a
// plausible number. The screens show hub-owned figures in their place and say
// so.
//
// `agents` likewise: nothing in the hub wires an agent to a project yet, so it
// is always `[]` and the card reads "No agent wired".

import { api, ApiError } from "@/lib/api";
import { relativeTime } from "./humanize";
import { getProjectKnowledge, getRepoKnowledge } from "./knowledge";
import type {
  Project,
  ProjectConfig,
  ProjectEnvironment,
  ProjectRepo,
  ProjectTestAccount,
  ProviderKey,
} from "./types";

/* ── Wire shapes ─────────────────────────────────────────────────────────── */

/** `ProjectSummaryOut` — non-secret card figures, batch-loaded by the hub. */
interface ProjectSummaryWire {
  repo?: string;
  repoUrl?: string;
  branch?: string;
  repoCount?: number;
  provider?: string;
  knowledgeStatus?: string;
  knowledgeConfidence?: number;
  ticketCount?: number;
}

interface ProjectWire {
  id: number;
  key: string;
  name?: string;
  shared?: boolean;
  createdAt?: string | null;
  updatedAt?: string | null;
  summary?: ProjectSummaryWire | null;
}

interface ProjectConfigWire {
  key: string;
  name?: string;
  workItemConnectionId?: number | null;
  repositoryConnectionId?: number | null;
  baseUrl?: string;
  repos?: Record<string, unknown>[];
  environments?: Record<string, unknown>[];
  testAccounts?: Record<string, unknown>[];
  manualAuth?: boolean;
  shared?: boolean;
}

/* ── Provider vocabulary ─────────────────────────────────────────────────── */

/**
 * The hub speaks two provider vocabularies and the UI a third.
 *
 *   connections + ticket sync : `azure_devops` | `jira` | `github`
 *   the tickets model docstring: `ado` | `jira` | `github`
 *   the design/UI            : `ado` | `jira` | `gh`
 *
 * Sync stamps a ticket with the *connection's* kind, so the wire value the UI
 * must send and read is the connection vocabulary. Both are accepted on read.
 */
const KIND_TO_PROVIDER: Record<string, ProviderKey> = {
  azure_devops: "ado",
  ado: "ado",
  azure: "ado",
  jira: "jira",
  github: "gh",
  gh: "gh",
};

/** What the hub expects back — the connection kind. */
export const PROVIDER_WIRE_KIND: Record<ProviderKey, string> = {
  ado: "azure_devops",
  jira: "jira",
  gh: "github",
};

export const providerFromKind = (kind: string): ProviderKey | null =>
  KIND_TO_PROVIDER[(kind ?? "").trim().toLowerCase()] ?? null;

export const PROVIDER_DISPLAY: Record<ProviderKey, string> = {
  ado: "Azure DevOps",
  jira: "Jira Cloud",
  gh: "GitHub",
};

/* ── Presentation derivations ────────────────────────────────────────────── */

/**
 * Initials-tile gradients. Hex belongs in the data layer, never in a `.tsx`:
 * `Glyph` documents a per-project gradient as *data* and applies it through the
 * computed-style exemption. Picked deterministically so a project keeps the
 * same tile between reloads.
 */
const GRADIENTS = [
  "linear-gradient(135deg,#ff4d5c,#c20d22)",
  "linear-gradient(135deg,#8b5cf6,#6366f1)",
  "linear-gradient(135deg,#22d3ee,#0e7490)",
  "linear-gradient(135deg,#f59e0b,#b45309)",
  "linear-gradient(135deg,#6ee7b7,#0f766e)",
  "linear-gradient(135deg,#c3cad6,#6b7280)",
];

const gradientFor = (key: string): string => {
  let hash = 0;
  for (let i = 0; i < key.length; i += 1) {
    hash = (hash * 31 + key.charCodeAt(i)) | 0;
  }
  return GRADIENTS[Math.abs(hash) % GRADIENTS.length];
};

/** "SW" from "Surveyor Web"; falls back to the first two characters. */
export const projectInitials = (name: string): string => {
  const words = name.trim().split(/[\s_\-./]+/).filter(Boolean);
  if (words.length >= 2) return (words[0][0] + words[1][0]).toUpperCase();
  return (words[0] ?? "?").slice(0, 2).toUpperCase();
};

/** Last-resort provider guess from a repository URL. Never invents a default. */
const providerFromRepoUrl = (url: string): ProviderKey | null => {
  const u = (url ?? "").toLowerCase();
  if (!u) return null;
  if (u.includes("dev.azure.com") || u.includes("visualstudio.com")) return "ado";
  if (u.includes("github.")) return "gh";
  if (u.includes("atlassian.net") || u.includes("jira")) return "jira";
  return null;
};

/* ── Decoders ────────────────────────────────────────────────────────────── */

const str = (v: unknown): string => (typeof v === "string" ? v : "");
const bool = (v: unknown): boolean => v === true;

const toRepo = (raw: Record<string, unknown>): ProjectRepo => ({
  name: str(raw.name),
  repoUrl: str(raw.repoUrl ?? raw.repo_url),
  defaultBranch: str(raw.defaultBranch ?? raw.default_branch),
  localRepoPath: str(raw.localRepoPath ?? raw.local_repo_path),
  default: bool(raw.default),
});

const toEnvironment = (raw: Record<string, unknown>): ProjectEnvironment => ({
  name: str(raw.name),
  baseUrl: str(raw.baseUrl ?? raw.base_url),
  notes: str(raw.notes),
});

const toTestAccount = (raw: Record<string, unknown>): ProjectTestAccount => ({
  role: str(raw.role),
  username: str(raw.username),
  notes: str(raw.notes),
  hasPassword: bool(raw.hasPassword),
});

const toConfig = (wire: ProjectConfigWire): ProjectConfig => ({
  key: wire.key,
  name: wire.name ?? "",
  workItemConnectionId: wire.workItemConnectionId ?? null,
  repositoryConnectionId: wire.repositoryConnectionId ?? null,
  baseUrl: wire.baseUrl ?? "",
  repos: (wire.repos ?? []).map(toRepo),
  environments: (wire.environments ?? []).map(toEnvironment),
  testAccounts: (wire.testAccounts ?? []).map(toTestAccount),
  manualAuth: bool(wire.manualAuth),
  shared: bool(wire.shared),
});

/** The repo a card and the detail header name — the default, else the first. */
export const defaultRepo = (config: ProjectConfig | null): ProjectRepo | null => {
  if (!config || config.repos.length === 0) return null;
  return config.repos.find((r) => r.default) ?? config.repos[0];
};

/* ── Reads ───────────────────────────────────────────────────────────────── */

/** `null` on 404 rather than throwing — an absent row is an answer, not a fault. */
const orNull = async <T>(promise: Promise<T>): Promise<T | null> => {
  try {
    return await promise;
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) return null;
    throw error;
  }
};

/** GET /projects/{key}/config. */
export const getProjectConfig = (key: string): Promise<ProjectConfig | null> =>
  orNull(
    api
      .get<ProjectConfigWire>(`/projects/${encodeURIComponent(key)}/config`)
      .then(toConfig),
  );

/** Mirrored work-item count. `pageSize=1` — only `total` is wanted. */
const countTickets = async (rowId: number): Promise<number> => {
  const page = await api.get<{ total?: number }>("/tickets", {
    query: { projectId: rowId, pageSize: 1 },
  });
  return page.total ?? 0;
};

const assemble = async (wire: ProjectWire): Promise<Project> => {
  const [config, tickets] = await Promise.all([
    getProjectConfig(wire.key),
    countTickets(wire.id),
  ]);

  const repo = defaultRepo(config);

  // An agent that indexed one repository wrote a row keyed `project::repo`;
  // one that indexed the project wrote `project`. Ask for the repo first (the
  // hub falls back to the project row itself), then for the project row —
  // which also covers a repo NAME containing a slash, where the repo-scoped
  // path cannot be addressed at all and the route 404s outright.
  const knowledge =
    (repo?.name ? await getRepoKnowledge(wire.key, repo.name) : null) ??
    (await getProjectKnowledge(wire.key));
  const provider =
    providerFromKind(knowledge?.provider ?? "") ??
    providerFromRepoUrl(repo?.repoUrl ?? "");
  const name = wire.name?.trim() || wire.key;

  return {
    id: wire.key,
    rowId: wire.id,
    name,
    repo: repo?.name || repo?.repoUrl || "",
    provider,
    providerName: provider ? PROVIDER_DISPLAY[provider] : "Not connected",
    branch: repo?.defaultBranch || knowledge?.body.branch || "",
    agents: [],
    initials: projectInitials(name),
    gradient: gradientFor(wire.key),
    updated: relativeTime(wire.updatedAt ?? wire.createdAt ?? null),
    shared: bool(wire.shared),
    tickets,
    knowledge,
    config,
  };
};

/**
 * Build a card from the hub's own `summary` — no per-project fan-out.
 *
 * The list used to call `assemble` for every row, costing config + ticket
 * count + one or two knowledge reads each (3N+1 requests to draw one screen).
 * The hub now batch-loads those figures in three queries and returns them on
 * the row, so the list is a single request.
 *
 * `config` and `knowledge` are left null here on purpose: the card does not
 * render them, and the list response deliberately carries no test-account
 * material. The detail screen still fetches the full objects.
 */
const fromSummary = (wire: ProjectWire): Project => {
  const s = wire.summary ?? {};
  const name = wire.name?.trim() || wire.key;
  const provider =
    providerFromKind(s.provider ?? "") ?? providerFromRepoUrl(s.repoUrl ?? "");
  return {
    id: wire.key,
    rowId: wire.id,
    name,
    repo: s.repo || s.repoUrl || "",
    provider,
    providerName: provider ? PROVIDER_DISPLAY[provider] : "Not connected",
    branch: s.branch || "",
    agents: [],
    initials: projectInitials(name),
    gradient: gradientFor(wire.key),
    updated: relativeTime(wire.updatedAt ?? wire.createdAt ?? null),
    shared: bool(wire.shared),
    tickets: s.ticketCount ?? 0,
    knowledge: null,
    config: null,
    /** Status string straight from the hub — the card's pill reads this. */
    knowledgeStatus: s.knowledgeStatus || "not_indexed",
    knowledgeConfidence: s.knowledgeConfidence ?? 0,
    repoCount: s.repoCount ?? 0,
  };
};

/**
 * GET /projects — one request. Falls back to the old per-project fan-out only
 * if the hub omitted `summary` (an older API than this client).
 */
export const getProjects = async (): Promise<Project[]> => {
  const rows = await api.get<ProjectWire[]>("/projects");
  if (rows.every((r) => r.summary)) return rows.map(fromSummary);
  return Promise.all(rows.map(assemble));
};

/** GET /projects/{key}. `null` when the key does not resolve for this caller. */
export const getProject = async (key: string): Promise<Project | null> => {
  if (!key) return null;
  const wire = await orNull(
    api.get<ProjectWire>(`/projects/${encodeURIComponent(key)}`),
  );
  return wire ? assemble(wire) : null;
};

/* ── Writes ──────────────────────────────────────────────────────────────── */

export interface CreateProjectInput {
  /** Registry key — the path parameter for every later call. Required. */
  key: string;
  name?: string;
  /** Admin-only; a non-admin asking for shared gets their own row. */
  shared?: boolean;
}

/** POST /projects. Hub audience only — an agent does not create projects. */
export const createProject = async (
  input: CreateProjectInput,
): Promise<Project> => {
  const key = input.key.trim();
  const wire = await api.post<ProjectWire>("/projects", {
    key,
    name: (input.name ?? "").trim() || key,
    shared: input.shared ?? false,
  });
  return assemble(wire);
};

/** PATCH /projects/{key} — rename. 403s on a shared row for a non-admin. */
export const renameProject = async (
  key: string,
  name: string,
): Promise<Project> => {
  const wire = await api.patch<ProjectWire>(
    `/projects/${encodeURIComponent(key)}`,
    { name },
  );
  return assemble(wire);
};

/**
 * `DELETE /projects/{key}` — remove the project and everything the hub owns
 * about it: its configuration (test-account passwords included), every
 * knowledge row for the key, and its directories in the workspace volume.
 * Hub audience only, and irreversible.
 *
 * **Mirrored work items block it.** The hub answers `409` naming how many
 * still reference the project rather than deleting or orphaning them; the
 * caller should surface `ApiError.message` verbatim, because it says what to do
 * next. Another member's project is a `404`, a shared one without admin a `403`.
 */
export const deleteProject = async (key: string): Promise<void> => {
  await api.delete(`/projects/${encodeURIComponent(key)}`);
};

/**
 * A partial `ProjectConfigIn`. Every field is optional — an omitted field
 * (`undefined`) is left untouched by the hub (`exclude_unset=True`); an
 * explicit `null` on a connection id un-binds it. `repos`/`environments`/
 * `testAccounts`, when present, REPLACE the stored array wholesale — the hub
 * has no per-row patch semantics for them, matching Q-Agent's one-shot Save.
 *
 * A blank `password` on a `ProjectTestAccountInput` preserves the stored
 * secret (the backend's rule) — never send a masked placeholder back as if
 * it were a real password.
 */
export interface ProjectConfigPatch {
  name?: string;
  workItemConnectionId?: number | null;
  repositoryConnectionId?: number | null;
  baseUrl?: string;
  repos?: {
    name: string;
    repoUrl?: string;
    defaultBranch?: string;
    localRepoPath?: string;
    default?: boolean;
  }[];
  environments?: { name?: string; baseUrl?: string; notes?: string }[];
  testAccounts?: {
    role?: string;
    username?: string;
    /** Blank keeps the stored password. */
    password?: string;
    notes?: string;
  }[];
  manualAuth?: boolean;
}

/**
 * PUT /projects/{key}/config. Hub audience only (`require_user`) — an agent
 * reads and PATCHes knowledge, but does not configure a project.
 *
 * The response re-reads through the same owner-masking rule as the GET, so
 * this always returns the config as the caller may see it, not the
 * unmasked patch that was sent.
 */
export const saveProjectConfig = async (
  key: string,
  patch: ProjectConfigPatch,
): Promise<ProjectConfig> =>
  toConfig(
    await api.put<ProjectConfigWire>(
      `/projects/${encodeURIComponent(key)}/config`,
      patch,
    ),
  );

/**
 * Slugify a display name into a registry key: `Atlas Reporting` →
 * `atlas-reporting`. The key is what every later URL is built from, so the
 * modal shows it and lets it be edited rather than deriving it silently.
 */
export const projectKeyFrom = (name: string): string =>
  name
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 60);
