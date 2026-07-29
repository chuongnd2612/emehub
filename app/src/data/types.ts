// Typed entities for every object the handoff's screens render.
//
// Identity is now fetched for real (`data/auth.ts`, `data/people.ts`); the
// rest still resolves from `data/fixtures/` behind a `// STUB (no endpoint
// yet):` marker. The shapes are the contract the screens code against, so
// swapping a stub for a real call stays a change inside `data/`.

/* ── Providers & agents ──────────────────────────────────────────────────── */

/** The three work-item providers. Exactly one is active on the Tickets page. */
export type ProviderKey = "ado" | "jira" | "gh";

export interface Provider {
  key: ProviderKey;
  /** Display name — "Azure DevOps" | "Jira Cloud" | "GitHub". */
  name: string;
  /** Single-letter glyph shown in the provider tile. */
  glyph: string;
  /** Brand colour token name to fill the tile with. */
  color: "azure" | "jira" | "github";
}

/** Q-Agent is live; D-Agent is a placeholder. */
export type AgentKey = "q" | "d";

export interface Product {
  key: AgentKey;
  name: string;
  /** Mono sub-line under the name. */
  code: string;
  live: boolean;
  role: string;
  description: string;
  tags: string[];
  /** The big number on the product card. */
  metric: string;
  metricLabel: string;
  stats: { k: string; v: string }[];
}

/* ── Projects & repositories ─────────────────────────────────────────────── */

export interface Project {
  id: string;
  name: string;
  /** Mono repo path, e.g. `emesoft/surveyor-web`. */
  repo: string;
  provider: ProviderKey;
  /** Provider display name as shown on the card. */
  providerName: string;
  branch: string;
  agents: AgentKey[];
  initials: string;
  /** CSS gradient for the initials tile. */
  gradient: string;
  tests: number;
  coverage: string;
  updated: string;
  indexed: boolean;
  lastIndexed: string;
  /** Knowledge confidence, 0–100. */
  confidence: number;
  needsRefresh: boolean;
  framework: string;
  /** Work items mirrored from the provider. */
  tickets: number;
  runs: number;
  passRate: string;
  /** Mono knowledge version, e.g. `v4`. */
  knowledgeVersion: string;
  repository: Repository;
}

export interface Repository {
  /** Detected stack chips. */
  stack: string[];
  /** Shared utilities the agents reuse (mono rows). */
  utils: string[];
  /** Indexed assets counter. */
  assets: number;
  pageObjects: number;
  fixtures: number;
}

/** Derived from `indexed` + `needsRefresh`. */
export type KnowledgeStatus = "indexed" | "needs-refresh" | "not-indexed";

export type KnowledgeSourceType = "Markdown" | "Document" | "URL" | "File";

export interface KnowledgeSource {
  id: string;
  projectId: string;
  title: string;
  type: KnowledgeSourceType;
  /** Human size, or an em dash for URL sources. */
  size: string;
  chunks: number;
  updated: string;
  scope: string;
  indexed: boolean;
}

/** One accordion section of "What the agents learned". */
export interface KnowledgeSection {
  key: string;
  label: string;
  body: string;
}

/* ── Tickets ─────────────────────────────────────────────────────────────── */

export type TicketStatus =
  | "New"
  | "In progress"
  | "In review"
  | "Blocked"
  | "Done";

export type ImportStatus = "Imported" | "Importing" | "Failed";

export interface Ticket {
  id: string;
  title: string;
  provider: ProviderKey;
  status: TicketStatus;
  /** Assigned agent, or null for "Unassigned". */
  agent: AgentKey | null;
  sync: ImportStatus;
  project: string;
  owner: string;
  /** Provider-variant fields. Only the keys in that provider's schema are set. */
  sprint?: string;
  area?: string;
  type?: string;
  epic?: string;
  priority?: string;
  milestone?: string;
  label?: string;
}

/** One filter pill / dropdown in the toolbar and the import dialog. */
export interface TicketFilterField {
  /** Matches a key on `Ticket`. */
  key: keyof Ticket | "owner";
  label: string;
  options: string[];
}

/** The whole filter set for one provider. Switching provider clears filters. */
export type TicketFilterSchema = Record<ProviderKey, TicketFilterField[]>;

/** Field key -> chosen value. An absent key means "Any". */
export type TicketFilters = Partial<Record<string, string>>;

export type ImportScope = "sprint" | "assigned" | "all";

export interface ImportRequest {
  provider: ProviderKey;
  mode: "basic" | "advanced";
  scope: ImportScope;
  filters: TicketFilters;
  /** Jira only. */
  jql?: string;
  /** GitHub only. */
  searchQuery?: string;
}

export interface ImportResult {
  /** Work items pulled. */
  count: number;
  provider: string;
  /** "active sprint" | "field filters applied" | … */
  scopeLabel: string;
}

/* ── Claude credentials ──────────────────────────────────────────────────── */

export type CredentialStatus = "active" | "expiring" | "expired";

/** Parsed from a `.credentials.json` and stored per workspace. */
export interface SharedCredential {
  id: string;
  label: string;
  email: string;
  /** Subscription tier, e.g. "Claude Max 20×". */
  subscription: string;
  /** Pre-formatted expiry date, e.g. "12 Oct 2026". */
  expiresDisplay: string;
  /** Days until expiry; null when the token has no expiry. */
  daysLeft: number | null;
  scopes: string[];
  lastRefreshed: string;
  /** Number of members assigned to this credential. */
  members: number;
  isDefault: boolean;
  /** The OAuth access token — masked in the UI unless revealed. */
  token: string;
  /** Where it came from, e.g. `.claude/.credentials.json · synced`. */
  source: string;
}

/** A member's own token, attached by dropping their `.credentials.json`. */
export interface PersonalCredential {
  filename: string;
  subscription: string;
  scopes: string[];
  token: string;
  expiresDisplay: string;
  daysLeft: number | null;
  lastRefreshed: string;
}

export type CredentialSource = "shared" | "personal";

/* ── Provider connections (Integrations) ─────────────────────────────────── */

export type ConnectionStatus = "Connected" | "Attention" | "Disconnected";

export type ConnectionFieldType = "text" | "password";

export interface ConnectionField {
  key: string;
  label: string;
  value: string;
  type: ConnectionFieldType;
}

export interface ProviderConnection {
  id: string;
  label: string;
  /** Mono one-liner, e.g. `dev.azure.com/emesoft/Surveyor`. */
  summary: string;
  status: ConnectionStatus;
  lastSync: string;
  fields: ConnectionField[];
}

export interface ProviderConnectionGroup {
  provider: ProviderKey;
  /** "4 projects" | "6 repositories". */
  projectsLabel: string;
  connections: ProviderConnection[];
}

export interface ConnectionTestResult {
  ok: boolean;
  /** Round-trip in ms, e.g. 118. */
  latencyMs: number;
}

/** Summary card on the Integrations page. */
export interface Integration {
  id: ProviderKey;
  name: string;
  state: ConnectionStatus;
  meta: string;
  auth: string;
  sync: string;
  last: string;
  items: string;
}

/* ── People & access ─────────────────────────────────────────────────────── */

/**
 * The four roles the handoff's Roles grid describes.
 *
 * The hub only *stores* two of them (`admin` | `member` — `api/app/models/
 * user.py › USER_ROLES`), so only "Admin" and "Member" round-trip through
 * `PATCH /auth/users/{id}`. "Owner" and "Viewer" exist in the design and in the
 * (stubbed) Roles grid; `ASSIGNABLE_ROLES` in `data/people.ts` is the subset the
 * API will actually accept, and the member role picker offers only that subset.
 */
export type RoleName = "Owner" | "Admin" | "Member" | "Viewer";

export interface Member {
  /** Hub user id — the path parameter for `PATCH|DELETE /auth/users/{id}`. */
  id: number;
  name: string;
  email: string;
  role: RoleName;
  /** Relative last-seen, e.g. "active now" / "3d ago" / "never". */
  lastActive: string;
  initials: string;
  /** Deactivated members still list, greyed, so an admin can re-enable them. */
  isActive: boolean;
  /** Live sessions for this member, from `AdminUserOut.sessionCount`. */
  sessionCount: number;
  /**
   * Which Claude credential this member runs on.
   *
   * STUB (no endpoint yet): nothing in the API maps a user to a Claude
   * credential, so this is always "none" for live rows. Kept on the type
   * because the handoff's Members table has a CLAUDE CREDENTIAL column and the
   * Roles fixtures still populate it.
   */
  credential: "shared" | "personal" | "none";
  /** SharedCredential id when `credential === 'shared'`. */
  credentialId: string | null;
}

export interface Role {
  name: RoleName;
  count: number;
  description: string;
  permissions: string[];
}

export interface Invitation {
  email: string;
  role: RoleName;
  sent: string;
  by: string;
}

/* ── Authentication ──────────────────────────────────────────────────────── */

/**
 * One row of `GET /auth/sessions`.
 *
 * The wire shape is `{id, userAgent, ip, createdAt, lastSeenAt, expiresAt,
 * current}` — there is no geo lookup on the hub, so the prototype's "where"
 * column has no source and is gone. `device` and `when` are derived client-side
 * from `userAgent` / `lastSeenAt` (see `data/auth.ts`).
 */
export interface Session {
  id: string;
  /** Derived from the User-Agent, e.g. "Windows · Chrome". */
  device: string;
  /** The raw User-Agent, shown as the row's tooltip. */
  userAgent: string;
  ip: string;
  /** Relative last-seen, e.g. "active now" / "26m ago". */
  when: string;
  /** Relative expiry, e.g. "in 30 days". Empty when the session has none. */
  expires: string;
  current: boolean;
}

/* ── The signed-in principal ─────────────────────────────────────────────── */

/** `UserOut` from the hub — the principal every authenticated call resolves. */
export interface AuthUser {
  id: number;
  email: string;
  firstName: string;
  lastName: string;
  /** Raw hub role: "admin" | "member". Use `roleName()` for the display name. */
  role: string;
  isActive: boolean;
  totpEnabled: boolean;
  createdAt: string | null;
  updatedAt: string | null;
  lastActive: string | null;
}

/** Enrolment material from `POST /auth/2fa/setup`. Contains the TOTP secret. */
export interface TotpSetup {
  secret: string;
  otpauthUri: string;
}

/**
 * The two shapes `POST /auth/login` can answer with. Discriminated on `kind`
 * so a caller cannot forget the MFA branch.
 */
export type LoginOutcome =
  | { kind: "authed"; user: AuthUser }
  | { kind: "mfa"; mfaToken: string };

export interface ApiKey {
  id: string;
  name: string;
  /** Visible key prefix; the remainder is never returned. */
  prefix: string;
  scope: string;
  used: string;
  created: string;
}

/* ── Overview ────────────────────────────────────────────────────────────── */

export type ActivityKind = "q" | "d" | "sync" | "kb" | "warn" | "key";

export interface ActivityEvent {
  text: string;
  /** Mono accent reference, e.g. `SUR-1428`. */
  ref: string;
  kind: ActivityKind;
  by: string;
  when: string;
  /** Icon name from components/ui/Icon. */
  icon: string;
}

export interface Kpi {
  label: string;
  value: string;
  unit: string;
  delta: string;
  direction: "up" | "down";
  /** Sparkline bar heights, 0–100. */
  bars: number[];
}
