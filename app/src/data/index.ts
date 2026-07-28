// The typed data layer — Handoff › State Management › "Data fetching
// (production)".
//
// EmeHub's API does not exist yet (repo is at Phase 0/1). Every function below
// is a STUB that resolves from `data/fixtures/` after the async delay the
// handoff specifies, and each carries a `// STUB:` comment naming the real
// endpoint that will replace it. Screens must import from HERE, never from
// `data/fixtures/*` directly, so swapping in the real API is a one-file change.
//
// CLAUDE.md: "Where an endpoint does not exist, stub it behind the typed data
// layer — and say so in your response. Never invent an API route silently."

import { SESSIONS, API_KEYS } from "./fixtures/auth";
import { CONNECTION_GROUPS } from "./fixtures/connections";
import { SHARED_CREDENTIALS } from "./fixtures/credentials";
import { KNOWLEDGE_SECTIONS, KNOWLEDGE_SOURCES } from "./fixtures/knowledge";
import { ACTIVITY, KPIS } from "./fixtures/overview";
import { INVITATIONS, MEMBERS, ROLES } from "./fixtures/people";
import { PROJECTS } from "./fixtures/projects";
import { INTEGRATIONS, PRODUCTS, PROVIDERS } from "./fixtures/providers";
import { TICKETS, TICKET_FILTER_SCHEMA } from "./fixtures/tickets";
import { CREDENTIAL_UPLOAD_DELAY_MS, parseCredentialFile, toPersonalCredential } from "./credentials";
import type {
  ActivityEvent,
  ApiKey,
  ConnectionTestResult,
  ImportRequest,
  ImportResult,
  Integration,
  Invitation,
  KnowledgeSection,
  KnowledgeSource,
  Kpi,
  Member,
  PersonalCredential,
  Product,
  Project,
  ProviderConnection,
  ProviderConnectionGroup,
  ProviderKey,
  Role,
  RoleName,
  Session,
  SharedCredential,
  Ticket,
  TicketFilters,
  TicketFilterSchema,
} from "./types";

export * from "./types";
export * from "./credentials";

/* ── Timings, from Handoff › "Async behaviours" ──────────────────────────── */

/** Import now — button spins for this long, then the success toast fires. */
export const IMPORT_DELAY_MS = 1500;
/** Test connection — "Testing…" spinner. */
export const TEST_CONNECTION_DELAY_MS = 1300;
/** Credential upload — "Reading token…" spinner, after the parse succeeds. */
export const CREDENTIAL_DELAY_MS = CREDENTIAL_UPLOAD_DELAY_MS;

/** Reads instantly in the prototype; kept tiny so screens still see a Promise. */
const READ_DELAY_MS = 0;

const after = <T>(value: T, ms: number): Promise<T> =>
  new Promise((resolve) => setTimeout(() => resolve(value), ms));

/* ── GET ─────────────────────────────────────────────────────────────────── */

// STUB: GET /api/projects
export const getProjects = (): Promise<Project[]> =>
  after(PROJECTS, READ_DELAY_MS);

// STUB: GET /api/projects/{projectId}
export const getProject = (projectId: string): Promise<Project | null> =>
  after(PROJECTS.find((p) => p.id === projectId) ?? null, READ_DELAY_MS);

/**
 * Filtering rule, verbatim from the handoff: `provider match && every set
 * field equals the ticket's field && query matches id|title|project`.
 */
// STUB: GET /api/tickets?provider={provider}&{...filters}
export const getTickets = (
  provider: ProviderKey,
  filters: TicketFilters = {},
  query = "",
): Promise<Ticket[]> => {
  const q = query.trim().toLowerCase();
  const rows = TICKETS.filter((t) => {
    if (t.provider !== provider) return false;
    for (const [key, value] of Object.entries(filters)) {
      if (value == null || value === "") continue;
      if ((t as unknown as Record<string, unknown>)[key] !== value) return false;
    }
    if (!q) return true;
    return `${t.id} ${t.title} ${t.project}`.toLowerCase().includes(q);
  });
  return after(rows, READ_DELAY_MS);
};

// STUB: GET /api/tickets/schema — the provider-variant filter fields.
export const getTicketFilterSchema = (): Promise<TicketFilterSchema> =>
  after(TICKET_FILTER_SCHEMA, READ_DELAY_MS);

// STUB: GET /api/projects/{projectId}/knowledge/sources
export const getKnowledgeSources = (
  projectId: string,
): Promise<KnowledgeSource[]> =>
  after(
    KNOWLEDGE_SOURCES.filter((k) => k.projectId === projectId),
    READ_DELAY_MS,
  );

// STUB: GET /api/projects/{projectId}/knowledge/sections
export const getKnowledgeSections = (
  _projectId: string,
): Promise<KnowledgeSection[]> => after(KNOWLEDGE_SECTIONS, READ_DELAY_MS);

// STUB: GET /api/credentials/claude/shared
export const getSharedCredentials = (): Promise<SharedCredential[]> =>
  after(SHARED_CREDENTIALS, READ_DELAY_MS);

// STUB: GET /api/connections
export const getConnections = (): Promise<ProviderConnectionGroup[]> =>
  after(CONNECTION_GROUPS, READ_DELAY_MS);

// STUB: GET /api/integrations — the per-provider summary cards.
export const getIntegrations = (): Promise<Integration[]> =>
  after(INTEGRATIONS, READ_DELAY_MS);

// STUB: GET /api/members
export const getMembers = (): Promise<Member[]> => after(MEMBERS, READ_DELAY_MS);

// STUB: GET /api/roles
export const getRoles = (): Promise<Role[]> => after(ROLES, READ_DELAY_MS);

/**
 * Pending invitations are the one collection two different surfaces mutate —
 * the global Invite modal creates, User Management revokes — so the stub keeps
 * its own mutable copy instead of handing the fixture array around.
 */
const INVITATION_STORE: Invitation[] = [...INVITATIONS];

// STUB: GET /api/invitations
export const getInvitations = (): Promise<Invitation[]> =>
  after([...INVITATION_STORE], READ_DELAY_MS);

// STUB: GET /api/auth/sessions
export const getSessions = (): Promise<Session[]> =>
  after(SESSIONS, READ_DELAY_MS);

// STUB: GET /api/auth/api-keys
export const getApiKeys = (): Promise<ApiKey[]> => after(API_KEYS, READ_DELAY_MS);

// STUB: GET /api/activity
export const getActivity = (): Promise<ActivityEvent[]> =>
  after(ACTIVITY, READ_DELAY_MS);

// STUB: GET /api/overview/kpis
export const getKpis = (): Promise<Kpi[]> => after(KPIS, READ_DELAY_MS);

// Static product metadata — Q-Agent and D-Agent. No endpoint planned.
export const getProducts = (): Promise<Product[]> =>
  after(PRODUCTS, READ_DELAY_MS);

export { PROVIDERS };

/* ── POST ────────────────────────────────────────────────────────────────── */

/**
 * Runs an import. Resolves after 1500 ms; the caller shows `Importing…` with a
 * spinning icon meanwhile, then toasts
 * `Import complete — 31 work items pulled from <provider> · <scope|field filters applied>`.
 */
// STUB: POST /api/tickets/import
export const runImport = (request: ImportRequest): Promise<ImportResult> => {
  const scopeLabel =
    request.mode === "advanced"
      ? "field filters applied"
      : { sprint: "active sprint", assigned: "items assigned to you", all: "all open items" }[
          request.scope
        ];
  return after(
    { count: 31, provider: PROVIDERS[request.provider].name, scopeLabel },
    IMPORT_DELAY_MS,
  );
};

/** Resolves after 1300 ms; the caller then marks the connection Connected. */
// STUB: POST /api/connections/{connectionId}/test
export const testConnection = (
  _connectionId: string,
): Promise<ConnectionTestResult> =>
  after({ ok: true, latencyMs: 118 }, TEST_CONNECTION_DELAY_MS);

// STUB: PUT /api/connections/{connectionId}
export const saveConnection = (
  connection: ProviderConnection,
): Promise<ProviderConnection> => after(connection, READ_DELAY_MS);

// STUB: DELETE /api/connections/{connectionId}
export const removeConnection = (_connectionId: string): Promise<void> =>
  after(undefined, READ_DELAY_MS);

/**
 * Parses the dropped `.credentials.json` for real (see ./credentials.ts), then
 * waits the handoff's 850 ms "Reading token…" dwell before resolving.
 */
// STUB: POST /api/credentials/claude (multipart .credentials.json)
export const uploadCredential = async (
  file: File,
): Promise<PersonalCredential> => {
  const parsed = await parseCredentialFile(file);
  return after(toPersonalCredential(parsed), CREDENTIAL_DELAY_MS);
};

// STUB: POST /api/credentials/claude/{credentialId}/rotate
export const rotateCredential = async (
  credentialId: string,
  file: File,
): Promise<SharedCredential> => {
  const parsed = await parseCredentialFile(file);
  const existing = SHARED_CREDENTIALS.find((c) => c.id === credentialId);
  const personal = toPersonalCredential(parsed);
  const rotated: SharedCredential = {
    id: credentialId,
    label: existing?.label ?? parsed.filename.replace(/\.json$/, ""),
    email: existing?.email ?? "—",
    subscription: personal.subscription,
    expiresDisplay: personal.expiresDisplay,
    daysLeft: personal.daysLeft,
    scopes: personal.scopes,
    lastRefreshed: "just now",
    members: existing?.members ?? 0,
    isDefault: existing?.isDefault ?? false,
    token: personal.token,
    source: `uploaded · ${parsed.filename}`,
  };
  return after(rotated, CREDENTIAL_DELAY_MS);
};

// STUB: DELETE /api/credentials/claude/{credentialId}
export const removeCredential = (_credentialId: string): Promise<void> =>
  after(undefined, READ_DELAY_MS);

// STUB: POST /api/credentials/claude/{credentialId}/default
export const setDefaultCredential = (
  credentialId: string,
): Promise<SharedCredential[]> =>
  after(
    SHARED_CREDENTIALS.map((c) => ({ ...c, isDefault: c.id === credentialId })),
    READ_DELAY_MS,
  );

/** Starts indexing. Immediate — the caller switches to the knowledge tab. */
// STUB: POST /api/projects/{projectId}/knowledge/build
export const buildKnowledge = (_projectId: string): Promise<void> =>
  after(undefined, READ_DELAY_MS);

// STUB: PATCH /api/members/{email}
export const changeRole = (email: string, role: RoleName): Promise<Member[]> =>
  after(
    MEMBERS.map((m) => (m.email === email ? { ...m, role } : m)),
    READ_DELAY_MS,
  );

// STUB: POST /api/invitations
export const invite = (email: string, role: RoleName): Promise<Invitation> => {
  const invitation: Invitation = {
    email,
    role,
    sent: "just now",
    by: "Emre Kaya",
  };
  INVITATION_STORE.unshift(invitation);
  return after(invitation, READ_DELAY_MS);
};

// STUB: DELETE /api/invitations/{email}
export const revokeInvitation = (email: string): Promise<void> => {
  const at = INVITATION_STORE.findIndex((i) => i.email === email);
  if (at >= 0) INVITATION_STORE.splice(at, 1);
  return after(undefined, READ_DELAY_MS);
};
