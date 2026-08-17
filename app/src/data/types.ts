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

/** Why the sign-in hand-off is unavailable — `api/app/config.py`. */
export type HandoffBlocker = "no_url" | "no_cookie_domain" | "domain_mismatch";

/**
 * One entry from `GET /agents` — where an agent lives and whether we can
 * actually hand a session to it.
 *
 * `registered` and `handoffReady` are **not** the same thing: an agent can be
 * registered (the hub mints it tokens) while single sign-on still cannot work,
 * because the refresh cookie will not reach its origin. See ADR 0008.
 */
export interface AgentTarget {
  /** The JWT audience — `qagent` | `dagent`. */
  id: string;
  key: AgentKey;
  name: string;
  url: string | null;
  registered: boolean;
  handoffReady: boolean;
  reason: HandoffBlocker | null;
}

export interface Product {
  key: AgentKey;
  name: string;
  /** Mono sub-line under the name. */
  code: string;
  /**
   * Design copy, **not** runtime state — it drives the "Live"/"Placeholder"
   * pill. D-Agent stays a placeholder even once a URL is configured for it.
   * Whether a launch is possible is `launchUrl` / `handoffReady` below.
   */
  live: boolean;
  role: string;
  description: string;
  tags: string[];
  /**
   * No `metric` / `metricLabel` / `stats`.
   *
   * The card used to carry "1,204 RUNS THIS MONTH", "38 SUITES", "96% PASS
   * RATE". Those are QAgent's run history: the hub owns identity, configuration
   * and knowledge metadata (ADR 0001), stores no run history, and has no
   * endpoint that could ever fill them. They were invented, so they are gone
   * rather than zeroed.
   */
  /** Merged from `GET /agents`. Null when the agent has no URL configured. */
  launchUrl?: string | null;
  /** Merged from `GET /agents`. False means a launch would fail after the click. */
  handoffReady?: boolean;
  /** Merged from `GET /agents`. Names the missing configuration. */
  handoffReason?: HandoffBlocker | null;
}

/* ── Projects & repositories ─────────────────────────────────────────────── */

/**
 * Lifecycle of a knowledge base, exactly as the hub stores it
 * (`api/app/models/knowledge.py › KNOWLEDGE_STATUSES`). `indexing` belongs to
 * whoever is building — the agent — and the hub only records the transition it
 * is told about.
 */
export type KnowledgeWireStatus =
  | "not_indexed"
  | "indexing"
  | "indexed"
  | "stale"
  | "error";

/**
 * The knowledge blob an agent reports (`KnowledgeOut.knowledge`).
 *
 * The hub stores it verbatim — it never produces one, because building a
 * knowledge base needs a repo clone and the Claude CLI on disk, neither of
 * which the hub has (ROADMAP.md Phase 4). Shape mirrors QAgent's
 * `KnowledgeBody`, which is what actually writes it.
 */
export interface KnowledgeBody {
  branch: string;
  /** Detected stack chips. */
  stack: string[];
  architecture: string;
  domain: string;
  /** The locator strategy the agent inferred — the test convention. */
  locator: string;
  assets: number;
  pageObjects: number;
  fixtures: number;
  /** Shared utilities the agents reuse (mono rows). */
  utilities: string[];
  baseUrl: string;
  routes: unknown[];
  selectors: unknown[];
  environments: { name?: string; baseUrl?: string; notes?: string }[];
  businessEntities: string[];
}

/** `KnowledgeOut` — the metadata row plus the blob. */
export interface KnowledgeMeta {
  id: number;
  key: string;
  projectKey: string;
  /** "" for the project-level row. */
  repo: string;
  name: string;
  /** Raw provider string the agent reported, e.g. "ado". May be "". */
  provider: string;
  framework: string;
  status: KnowledgeWireStatus;
  /** Knowledge confidence, 0–100. */
  confidence: number;
  /** Mono knowledge version, e.g. `v4`. */
  version: string;
  needsRefresh: boolean;
  /** ISO timestamp, or null when it has never been indexed. */
  lastIndexed: string | null;
  /** Relative form of the above — "2h ago" / "never". */
  lastIndexedLabel: string;
  /** Agent-host directory holding knowledge.md/.json. Opaque to the hub. */
  docPath: string;
  lastError: string;
  shared: boolean;
  body: KnowledgeBody;
  /** Live build progress — see {@link KnowledgeBuildProgress}. */
  build: KnowledgeBuildProgress;
}

/** One stage of a hub-side knowledge build, in the order they happen. */
export type KnowledgeBuildStage =
  | "queued"
  | "resolving"
  | "cloning"
  | "analyzing"
  | "writing";

/**
 * What the hub is actually doing right now (issue #68).
 *
 * Every field is read back from the row the build worker writes, so a reload
 * picks the build up where it is instead of restarting a local animation.
 * `stage` is `""` when nothing is in flight.
 */
export interface KnowledgeBuildProgress {
  stage: KnowledgeBuildStage | "";
  /** 1-based ordinal of `stage`; 0 when there is none. */
  step: number;
  /** How many stages there are — the hub's count, not a hard-coded one. */
  totalSteps: number;
  /** The live line. During `analyzing` it follows Claude's own event stream. */
  message: string;
  /** ISO timestamp the current (or last) build started — the elapsed clock. */
  startedAt: string | null;
  /**
   * The row says `indexing` but no worker is behind it: a build orphaned by a
   * restarted container. Offer a retry; never keep spinning.
   */
  orphaned: boolean;
}

/** One configured repository — `ProjectConfigOut.repos[]`. */
export interface ProjectRepo {
  name: string;
  repoUrl: string;
  defaultBranch: string;
  /** Path on the AGENT host. Stored and echoed; never resolved by the hub. */
  localRepoPath: string;
  default: boolean;
}

export interface ProjectEnvironment {
  name: string;
  baseUrl: string;
  notes: string;
}

/** Passwords are never rendered — the config read returns `hasPassword`. */
export interface ProjectTestAccount {
  role: string;
  username: string;
  notes: string;
  hasPassword: boolean;
}

/** `ProjectConfigOut`, minus the plaintext passwords we never display. */
export interface ProjectConfig {
  key: string;
  name: string;
  workItemConnectionId: number | null;
  repositoryConnectionId: number | null;
  baseUrl: string;
  repos: ProjectRepo[];
  environments: ProjectEnvironment[];
  testAccounts: ProjectTestAccount[];
  manualAuth: boolean;
  shared: boolean;
}

/**
 * A registry row, joined with its configuration, its knowledge metadata and its
 * mirrored work-item count.
 *
 * The handoff's card also shows `tests`, `coverage`, `runs` and `passRate`.
 * Those are QAgent's run history; the hub owns identity, configuration and
 * knowledge *metadata* only (ADR 0001, ROADMAP Phase 4), so there is nothing
 * behind them here and they are deliberately absent rather than invented.
 */
export interface Project {
  /** Registry key — accepted as the path parameter by every `/projects` endpoint. */
  id: string;
  /**
   * Stable external identity (#150), and what the app **routes by**.
   *
   * The key makes a poor URL: it is derived from the name and is unique only
   * within one owner's namespace, so two members can each have a `surency`, and
   * a rename changes the address of a page somebody bookmarked. The GUID changes
   * under neither.
   *
   * Endpoints accept both, so a key-shaped URL still resolves — old links, and
   * anything already deep-linking by key, keep working.
   */
  guid: string;
  /** Numeric row id — the `projectId` filter on `GET /tickets`. */
  rowId: number;
  name: string;
  /** Mono repo path from the default configured repo. "" when none. */
  repo: string;
  /** null when neither the config nor the knowledge row names a provider. */
  provider: ProviderKey | null;
  /** Provider display name, or "Not connected". */
  providerName: string;
  /** Default branch. "" when unknown. */
  branch: string;
  /**
   * Agents wired to this project. The hub has no field for this yet, so it is
   * always empty for live rows and the UI reads "No agent wired".
   */
  agents: AgentKey[];
  initials: string;
  /** CSS gradient for the initials tile — derived from the key. */
  gradient: string;
  /** Relative `updatedAt`. */
  updated: string;
  shared: boolean;
  /** Work items mirrored — the `total` of `GET /tickets?projectId=…`. */
  tickets: number;
  /**
   * null when the project has no knowledge row (the hub answers 404) — and
   * always null on a LIST read, which carries `knowledgeStatus` instead so
   * the screen costs one request rather than 3N+1. The detail read fills it.
   */
  knowledge: KnowledgeMeta | null;
  /** null when the config read failed, the caller may not see it, or this
   * came from a list read (the list response carries no config). */
  config: ProjectConfig | null;
  /**
   * Raw knowledge status from the hub's list summary (`indexed`, `stale`,
   * `not_indexed`, …). Present on list rows, where `knowledge` is null.
   */
  knowledgeStatus?: string;
  /** Confidence from the list summary, when `knowledge` is null. */
  knowledgeConfidence?: number;
  /** How many repositories are configured — list summary only. */
  repoCount?: number;
}

/** Derived from the knowledge row for the status pill. */
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

/**
 * One row of `GET /tickets`.
 *
 * Provider states and work-item types are project-configurable free text, so
 * `status`, `type` and `priority` are plain strings rather than the handoff's
 * closed sets — `statusTone()` maps the known ones and falls back to neutral.
 *
 * The handoff's AGENT and IMPORT columns have no source: the hub does not
 * assign agents to work items, and every stored row is imported by definition
 * (it exists because a sync put it there). `synced` replaces IMPORT.
 */
export interface Ticket {
  /** The provider's own identifier, e.g. `SUR-1428`. */
  id: string;
  title: string;
  provider: ProviderKey | null;
  status: string;
  /** Provider work-item type — "Bug", "User Story", "Story"… */
  type: string;
  priority: string;
  /** Hub project key this row is attributed to. "" when unattributed. */
  project: string;
  /** The provider-side assignee. */
  owner: string;
  sprint: string;
  area: string;
  epic: string;
  labels: string[];
  acCount: number;
  /**
   * The work item's page in the provider (INTEGRATION.md §3 › *The work item's
   * own URL*). `""` means the hub has **no link to offer** — an adapter without
   * an org or base URL configured cannot build one — so render a link only when
   * this is non-empty and never construct a fallback.
   */
  url: string;
  /** Relative `syncedAt`, e.g. "26m ago". */
  synced: string;
  /** ISO `syncedAt` — drives the toolbar's "last import" line. */
  syncedAt: string | null;
}

/** One comment from the snapshot taken at `syncedAt`. */
export interface TicketComment {
  who: string;
  /** The provider's own timestamp string, already humanised upstream. */
  when: string;
  text: string;
}

/** A provider attachment. `size` is the provider's string, unparsed. */
export interface TicketAttachment {
  name: string;
  size: string;
}

/** A pull request the provider has linked to the work item. */
export interface LinkedPullRequest {
  repo: string;
  /** A string: GitHub numbers and Azure DevOps ids are not the same thing. */
  num: string;
  title: string;
  status: string;
  url: string;
}

/**
 * `GET /tickets/{externalId}` — the row plus everything the list omits.
 *
 * Extends `Ticket` so the table's row and the detail's header render from the
 * same fields, and a caller that already holds a `Ticket` can widen rather than
 * re-map.
 *
 * QAgent's `note` is absent, and stays absent: it is a QA-run annotation, which
 * is domain work the hub does not do (`api/app/models/ticket.py`).
 */
export interface TicketDetail extends Ticket {
  description: string;
  /** The criteria split into a list — empty when they did not divide cleanly. */
  acceptanceCriteria: string[];
  /** The provider's original AC markup. Must be sanitized before rendering. */
  acceptanceCriteriaHtml: string;
  comments: TicketComment[];
  attachments: TicketAttachment[];
  linkedPrs: LinkedPullRequest[];
}

/**
 * One provider-side test case from `GET /tickets/{externalId}/test-cases`.
 *
 * `url` may be `""` where the adapter cannot build one — optional, not broken.
 */
export interface ProviderTestCase {
  externalId: string;
  title: string;
  state: string;
  url: string;
}

/**
 * A read that went through to the provider — `{items, supported}` rather than a
 * bare array, because an empty list means three different things and only one
 * of them is "there are none" (INTEGRATION.md §3).
 */
export interface ProviderRead<T> {
  items: T[];
  /** `false` when the provider has no such concept — Jira has no test cases. */
  supported: boolean;
}

export interface ProviderTestCaseRead extends ProviderRead<ProviderTestCase> {
  /**
   * `true` when the provider answered for the whole project rather than this
   * work item. Azure DevOps always does.
   */
  projectWide: boolean;
}

/** One page of `GET /tickets`. Filtering and paging are server-side. */
export interface TicketPage {
  items: Ticket[];
  total: number;
  page: number;
  pageSize: number;
}

/** One filter pill / dropdown in the toolbar and the import dialog. */
export interface TicketFilterField {
  /** Local key, also the `TicketFilters` key. */
  key: string;
  label: string;
  /** The `GET /tickets` query parameter this pill drives. */
  param: string;
  /** Distinct values present in the hub's store for the active provider. */
  options: string[];
}

/** The whole filter set for one provider. Switching provider clears filters. */
export type TicketFilterSchema = Record<ProviderKey, TicketFilterField[]>;

/** Field key -> chosen value. An absent key means "Any". */
export type TicketFilters = Partial<Record<string, string>>;

export type ImportScope = "sprint" | "assigned" | "all";

export interface ImportRequest {
  provider: ProviderKey;
  /** Which tab composed the query. Only affects the wording of the result. */
  mode: "basic" | "advanced";
  /** Which Basic preset was chosen. Only affects the wording of the result. */
  scope: ImportScope;
  /**
   * The clause query to import (`data/ticketQuery`) — the **only** selection the
   * hub accepts (#130). Basic composes one from its scope
   * (`components/import/scopes.ts`), Advanced from the builder. Absent means
   * nothing was applied, and the dialog will not let it be submitted.
   */
  query?: import("./ticketQuery").TicketQuery;
}

export interface ImportResult {
  /** Work items pulled. */
  count: number;
  provider: string;
  /** "active sprint" | "field filters applied" | … */
  scopeLabel: string;
}

/* ── Claude credentials ──────────────────────────────────────────────────── */

/**
 * `refreshable` is not in the original handoff — it arrived with issue #63. A
 * Claude OAuth *access* token lives hours, so a real `.credentials.json` is
 * past its `expiresAt` almost immediately; the refresh token beside it means
 * the CLI renews it on the next run. Calling that `expired` turned every
 * uploaded credential red, and calling it `active` would overstate its health,
 * so it is its own state. Mirrors `derived_status` in
 * `api/app/services/claude_credentials.py`.
 */
export type CredentialStatus =
  | "active"
  | "expiring"
  | "refreshable"
  | "expired";

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
  /** Expiry as epoch ms — `daysLeft` rounds, the status rule must not. */
  expiresAtEpochMs: number | null;
  /** Whether a refresh token sits beside the access token (issue #63). */
  hasRefreshToken: boolean;
  /** The hub's stored status column — `expired` here is the CLI's verdict. */
  storedStatus: string;
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

// `ConnectionField`, `ProviderConnection`, `ProviderConnectionGroup` and
// `ConnectionTestResult` used to live here, shaped for the fixture era. The
// live wire shapes replaced them when Integrations was wired to the API and
// are defined in `data/connections.ts` (`ConnectionFormField`, `Connection`,
// `ConnectionGroup`, `ConnectionTestOutcome`) — the old ones were unreferenced
// and are deleted rather than left as a second, wrong answer to "what is a
// connection". `ConnectionFieldType` stays: `connections.ts` still uses it.

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

/* ── Overview ────────────────────────────────────────────────────────────── */

export type ActivityKind = "q" | "d" | "sync" | "kb" | "warn" | "key";

export interface ActivityEvent {
  /**
   * Stable identity — the audit row's own id.
   *
   * The feed used to key on `ref`-`when`, which is unique across a handful of
   * invented events and emphatically not across real ones: two "Signed in"
   * rows against the same actor minutes apart collide, and React drops one.
   */
  id: string;
  text: string;
  /** Mono accent reference, e.g. `SUR-1428`. */
  ref: string;
  kind: ActivityKind;
  by: string;
  when: string;
  /** Icon name from components/ui/Icon. */
  icon: string;
}

/**
 * One Overview tile.
 *
 * No `delta`, `direction` or `bars`. The handoff's tile carries a delta chip and
 * an 8-bar sparkline, and each of those needs history the hub does not keep — so
 * they could only ever have been invented, and were. They belong back the moment
 * the hub records a time series, and not before.
 */
export interface Kpi {
  label: string;
  value: string;
  unit: string;
}
