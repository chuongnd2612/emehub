# EmeHub — Integration contract

The specification QAgent and DAgent implement in order to be part of the suite.

Status: **the hub side is built. QAgent consumes identity; nothing else is consumed by anyone.**
Everything in §2 and §3 is live against the running API — you can call it today.

- **Identity — done.** QAgent validates hub tokens, JIT-provisions a local user from `sub`, and
  establishes its own session from the handed-over token, behind `QAGENT_HUB_SSO_ENABLED`
  (q-agent#476, slices B1–B5). Sign in at the hub, land in QAgent authenticated.
- **Everything else — not started.** No agent reads a credential, a project, a knowledge base or a
  ticket from here, so for those the hub still runs *in parallel* with both agents rather than in
  front of them.
- **DAgent consumes nothing**, and the blocker is on its side: no user model exists to receive an
  identity (§6.1).

See [ROADMAP.md](ROADMAP.md) Phases 3–5.

---

## 1. Principles

1. **The hub authenticates; agents authorise.** The hub decides *who you are*. Each agent
   decides what you may do inside it, from the role in the token.
2. **No shared database.** Agents never open a connection to the hub's Postgres. Everything
   crosses an HTTP boundary. ([ADR 0003](adr/0003-integration-via-http-and-hub-issued-jwt.md))
3. **No per-request callback.** Access tokens are validated locally by signature. A hub
   outage must not make agents unusable for work already in flight.
4. **Fail closed on secrets, degrade open on reads.** A stale cached project list is fine; a
   stale or unavailable Claude credential is not — see §5.

---

## 2. Token

The hub issues short-lived HS256 access tokens.

```json
{
  "sub":   "9f1c…",            // user id
  "email": "duna.nguyen@emesoft.net",
  "role":  "admin",            // admin | member
  "sid":   "3a7e…",            // hub session id — revoking the session kills every agent
  "aud":   "qagent",           // qagent | dagent | emehub
  "iss":   "emehub",
  "iat":   1785312000,
  "exp":   1785312900          // 15 minutes
}
```

**Agents MUST validate**: signature, `iss == "emehub"`, `aud` equals their own id, and `exp`.
An agent that accepts a token minted for a different `aud` is a bug, not a convenience.

**Agents MUST NOT** issue, refresh, or extend tokens. Refresh happens only at the hub:

```
POST /auth/refresh        (hub, HttpOnly refresh cookie)  → new access token per audience
```

**Session revocation.** An agent SHOULD treat `sid` as a cache key and drop cached
per-session state when a token with a new `sid` arrives. Immediate cross-agent revocation
(pushing "session X is dead" to agents) is deferred; with a 15-minute expiry the worst case is
a 15-minute window.

### Getting the first token — the sign-in hand-off

An agent deployed on a sibling subdomain of the hub obtains its first token from the browser,
using the shared refresh cookie ([ADR 0008](adr/0008-cross-app-session-handoff.md)):

```
POST /auth/agent-token        { "audience": "qagent" }
  credentials: 'include'      → sends the shared emehub_refresh cookie
  X-CSRF: <emehub_csrf>       → the readable double-submit cookie
  → { accessToken, audience, expiresIn, user }
```

It returns a token for **that audience only**, and no refresh material. The hub's own audience is
refused: the hub SPA uses `/auth/refresh`, and handing an agent origin a hub-audience token would
let it reach hub-only routes.

> **Agents MUST call `/auth/agent-token`, never `/auth/refresh`.** `/auth/refresh` **rotates** the
> refresh token, so two applications sharing one cookie race — whichever silent refresh lands
> second presents a dead token and logs a live session out. `/auth/agent-token` deliberately does
> not rotate, which is what makes the cookie safe to share. Every call is audited, because this is
> the one path that accepts the refresh token without rotating it.

This requires the hub and the agent to be same-site: set `EMEHUB_COOKIE_DOMAIN` to the shared
parent (e.g. `.chuongnd.click`) and add the agent's origin to `EMEHUB_CORS_ORIGINS`. An agent on an
unrelated registrable domain cannot use this path; that case needs a short-lived single-use
hand-off code redeemed server-to-server, recorded as the fallback in ADR 0008 and not built.

The agent is expected to establish **its own** session from the token it receives, so the hub token
is consumed once at bootstrap rather than held. An agent that instead keeps using hub tokens for
onward reads runs into the 15-minute expiry with no way to refresh — see §5.

### Run-scoped credential grants — for work that outlives the token

The 15-minute expiry is a real wall for one case: an agent's **background run**. There is no browser
and no refresh cookie on a daemon thread, so `/auth/agent-token` is unavailable, and a run whose
Claude-credential need arrives after minute 15 would have no legal path — while §5 forbids proceeding
on a stale credential.

So an agent may exchange a live access token, **once at run start**, for a grant
([ADR 0009](adr/0009-run-scoped-credential-grants.md)):

```
POST /auth/agent-grant        { "runId": "…" }        Authorization: Bearer <agent access token>
  → { grant, audience, scope: "claude-credential", runId, expiresIn }   // default 4h, capped 24h
```

**A grant is not an access token, and reaches exactly three endpoints:**
`GET /credentials/claude/resolve`, `PUT /credentials/claude/refreshed` and
`POST /credentials/claude/usage`. Presented anywhere else it is a `401` — its audience
(`emehub:grant`) is never registerable, so it fails the access-token decoders structurally rather
than by a check.

What agents must know:

- **Mint it early**, while the access token is still valid. Minting requires an access token, so a
  grant cannot renew itself and there is no grant→grant chain.
- **`runId` is opaque to the hub.** It is recorded in the grant and in the audit trail; the hub never
  interprets it.
- **Revoking the hub session kills a live grant**, on its next use. `sid` is carried and re-checked,
  so §2's "revoking the session kills every agent" applies to grants unchanged.
- **An expired grant is a `401`, and that means refuse** — mint a new one if the session is still
  live, and otherwise stop. It does **not** mean the hub is down; see §5 for the distinction that
  matters to the user.
- The hub's own audience cannot mint one. A grant is for a background agent run.

Operator setting: `EMEHUB_AGENT_GRANT_TTL_MINUTES` (default `240`, hard cap `1440`; out of range is a
startup failure, not a clamp). There is no setting that disables grants — nothing here is an
authentication bypass.

### Key distribution

**Phase 1 — shared secret.** All three deployments are ours; `EMEHUB_JWT_SECRET` is
distributed as an environment variable and agents verify HS256 with it.

**Phase 3 — asymmetric + JWKS.** The hub signs RS256 and publishes
`GET /.well-known/jwks.json`; agents fetch and cache the public key. This removes the shared
secret and makes key rotation possible without redeploying every agent. Called out now so the
`kid` header is present from day one and the upgrade is not a breaking change.

---

## 3. Endpoints agents consume

All require a valid access token. All are read-only from the agent's perspective unless
noted.

| Method | Path | Returns |
|---|---|---|
| `GET` | `/me` | The authenticated user: id, email, name, role. |
| `GET` | `/credentials/claude/resolve` | The Claude credential this user should run with, already resolved through the own → shared → none precedence. Returns the credential material; see §4. |
| `GET` | `/connections` | Provider connections visible to the user, with their capabilities (`work_item`, `repository`). Never includes the PAT. |
| `POST` | `/connections/{id}/proxy` | *(deferred)* Ask the hub to make a provider call on the agent's behalf, so the PAT never leaves the hub. See §4. |
| `GET` | `/projects` | Project registry. Each row carries a `summary` of non-secret card figures (repo, branch, counts, knowledge status) so a list screen costs one request, not 3N+1. **No test-account material, not even `hasPassword`.** |
| `GET` | `/projects/{key}` | One project, same shape as a list row. |
| `GET` | `/projects/{key}/config` | Full project configuration including repositories. Test-account passwords are returned **only to the owning user** — a shared config (`owner_id IS NULL`) is owned by nobody, so its accounts stay masked even for an admin. |
| `GET` | `/projects/{key}/knowledge` | Project-level knowledge. 404 when the project has no knowledge row. |
| `GET` | `/projects/{key}/repos/{repo}/knowledge` | Per-repository knowledge base; falls back to the project-level row. |
| `PATCH` | `/projects/{key}/repos/{repo}/knowledge` | **Write.** Contribute discovered entries (QAgent's runtime selector discovery). Must not clobber existing `verified_at_runtime` entries. |
| `PUT` | `/projects/{key}/repos/{repo}/knowledge` | **Write.** Report the result of a build the agent ran on its own host — status, blob, confidence, and `docPath` (an opaque agent-host path the hub stores and never resolves). |
| `GET` | `/tickets` | Synced tickets, paged and filterable by project, provider, connection, state, assignee, sprint and free text. |
| `GET` | `/tickets/{external_id}` | One ticket, normalised. Optional `?providerKind=` disambiguates the same id across providers. |
| `GET` | `/tickets/{external_id}/comments` | The work item's comment thread, read **live** from the provider through the hub's own PAT. `{items, supported}`. |
| `GET` | `/tickets/{external_id}/test-cases` | Provider-side test cases, for continuing existing numbering when generating. `{items, supported, projectWide}`. |
| `POST` | `/tickets/{external_id}/comments` | **Write, to the provider.** Post a comment on the work item. `{body, attachments?}` → `{externalCommentId}`. |
| `POST` | `/tickets/{external_id}/state` | **Write, to the provider.** Transition the work item. `{targetStatus}` → the ticket as the hub now holds it. |
| `POST` | `/tickets/{external_id}/test-cases` | **Write, to the provider.** Create test cases in one pass. `{cases[], link?}` → per-case outcomes. |
| `POST` | `/tickets/sync` | **Write.** Pull work items from a provider and upsert them. Takes a **clause query** or `ticketIds` — see *Saying what to sync* below; the legacy `mode`/`sprint`/`states` fields are gone (#130). **The hub makes the provider call with its own stored PAT.** |
| `POST` | `/tickets/query/preview` | What a clause query *would* pull, without importing it. `{total, sample[], description}`. |
| `POST` | `/tickets/search` | The same clause query over the hub's own mirror, paged. A POST because a clause list does not fit a query string. |
| `DELETE` | `/tickets/{external_id}` | **Write.** Drop a mirrored row the caller can already see. Local only: it never touches the provider, so a re-sync restores it. |
| `POST` | `/audit/events` | **Write.** Append an audit event attributed to the calling agent. |

Agents MAY cache any `GET` above. Cache lifetime is the agent's choice; the hub sets
`Cache-Control` as a hint, not a rule.

### Ticket sync: the hub calls the provider, so the PAT does not have to move

`POST /tickets/sync` is in this table on purpose, and it settles a question that has been read the
wrong way round. Syncing work items needs a provider PAT — and §4 says the PAT never leaves the hub.
Those two facts do **not** add up to "an agent cannot own ticket sync". The agent names a connection
or a provider kind; **the hub** resolves it, decrypts its own PAT, calls the provider, and upserts
into the caller's own rows. The secret never crosses the boundary because it never needs to: the
call happens on the side that holds it.

Sync and delete are gated the same way as the reads (`require_principal` — any registered audience)
because neither is a hub-administration action. Both are scoped through
`app.services.ownership` to rows the caller can already see, so an agent can no more sync into
another member's tickets than it can read them. A ticket owned by someone else 404s rather than
403s, here as everywhere.

This is the pattern to reach for whenever an agent needs a provider operation — a narrow,
purpose-built endpoint where the hub picks the upstream from data it already owns. The caller names
a **ticket**, never a URL. That is what distinguishes it from the generic
`POST /connections/{id}/proxy` in §4, which stays deferred precisely because a caller-directed
forwarder is an SSRF and header-leak surface. The narrow endpoints have neither, and after them
there is no agent operation left that the generic one is needed for.

`GET /tickets/{external_id}/comments` and `…/test-cases` are the same arrangement for reads.

### Reading through to the provider: `supported` is not the same as empty

Both read-throughs answer `{items, supported}` rather than a bare array, because three different
things can happen and only one of them is "there are none":

| Outcome | Response |
|---|---|
| The provider has no such concept — Jira has no test cases; neither do GitHub issues | `200 {items: [], supported: false}` |
| There genuinely are none | `200 {items: [], supported: true}` |
| The provider call failed | `502` — **never** an empty list |
| No work-item-capable connection routes this ticket | `404` (a routing gap, not a provider failure) |
| The stored PAT cannot be decrypted under the current key | `502` (never passed on as an empty credential) |

An agent that treats an empty array as "no comments" will be wrong two ways out of three, so branch
on `supported` and treat a non-2xx as *unknown*, never as *none*. This is the same distinction §5
draws for the hub as a whole, applied one level down.

`GET …/test-cases` additionally reports **`projectWide`**. Azure DevOps has no cheap per-work-item
test-case query and answers for the entire project; the ticket in the path selects the *connection*,
not the result set. `projectWide: true` means "these are the project's cases, not this ticket's" —
treat them as scoped and you will over-count.

The comment shape is `{who, when, text}`, deliberately identical to the `comments` snapshot on
`GET /tickets/{external_id}`. Same shape, different freshness: the snapshot is as of `syncedAt`,
this endpoint is current. One concept, one shape.

### Saying what to sync: a clause query

**Breaking change, emehub#130.** `POST /tickets/sync` used to take a small filter language —
`mode` / `sprint` / `sprintPath` / `areaPath` / `states` / `workItemTypes`. Those fields are **gone**,
and the body now `extra="forbid"`s them, so a caller still sending one gets a `422` naming it rather
than a silent whole-project pull. Refusing is the point: an *ignored* filter returns **more** work
items than were asked for, which is the failure a caller is least likely to notice.

A body now names one of exactly two things:

| Field | Means |
|---|---|
| `query` | a **clause query** — the filter. Validated, then compiled per provider. |
| `ticketIds` | known work items by external id. Not a filter; there is no clause for it. |

With neither, the request is a `422` (*"Say what to import…"*). "Everything in the project" is
expressible — it is a `query` of `state is not <the finished states>` — but it has to be *asked for*
rather than arrived at by omitting every field.

```jsonc
// POST /tickets/sync
{ "providerKind": "azure_devops",          // or "connectionId": 7
  "query": {
    "clauses": [ { "field": "assignee", "operator": "is",    "values": ["@Me"] },
                 { "field": "state",    "operator": "in",    "values": ["Active", "Committed"] } ],
    "match": "all",                        // "any" ORs them. Not accepted for GitHub — see below.
    "sort":  { "field": "changedDate", "direction": "desc" } } }
```

**Fields**: `workItemType` `state` `assignee` `areaPath` `iterationPath` `tags` `title`
`changedSince` `createdSince` `parentId` `priority` `epic`.
**Operators**: `is` `isNot` `in` `notIn` `contains` `notContains` `under` `onOrAfter` `onOrBefore`.

The clause list is **flat**, with one global `match`. No nesting, deliberately: mixed AND/OR trees
are a large jump in both UI and compiler complexity and nothing anyone has asked for needs them.

**Macros are provider-neutral.** `@Me`, `@CurrentIteration`, `@Today`, `@Today - N` are written the
same way whatever the destination, and each compiler translates: Azure DevOps sees `@Me`, Jira
`currentUser()`, GitHub `@me`. Anything else beginning with `@` is a literal value — the compilers
match an exact allow-list, never a leading `@`, so `@Me OR 1=1` is quoted as the string it is.

**Not every provider can express every clause, and the hub says so rather than dropping one.** A
clause a destination cannot run is a `422` carrying `{problems: [{message, clauseIndex}]}` — the same
validation the hub's own UI greys out its Apply button with, so "the button was disabled" and
"400 Bad Request" always agree. The differences are real:

| Destination | Cannot | Because |
|---|---|---|
| Azure DevOps | — | full WIQL |
| Jira | `areaPath`; `under` on `iterationPath` | no area tree; a sprint is matched by name or id, not a path prefix |
| GitHub | `areaPath` `iterationPath` `parentId` `priority` `epic`; **`match: "any"`** | search takes qualifiers, not a query language — and every qualifier ANDs, with no OR and no grouping |

Ask what a query *would* pull before pulling it with **`POST /tickets/query/preview`**
(`{connectionId?, providerKind?, project?, query}` → `{total, sample[], description}`). Nothing is
written, the count is the provider's own uncapped total rather than the capped fetch, and
`description` is the query in prose. And **`POST /tickets/search`** runs the same clause model over
the hub's *mirror* (`{query, q?, providerKind?, projectId?, page?, pageSize?}` → a ticket page) — a
POST because a clause list does not fit a query string honestly. `GET /tickets` is unchanged.

### Writing back to the provider

The three `POST /tickets/{external_id}/…` writes are the reason an agent can stop holding provider
credentials at all: they are the provider side of QAgent's Publish and Link screens, performed by
the hub so the PAT never leaves. Same routing as the reads — the ticket selects the connection, the
caller never names an upstream.

**A comment and a transition are two calls, and that is deliberate.** A publish flow posts a comment
and *then* transitions, and it must be able to report a comment that published while its transition
failed. One combined endpoint could not express that state, so it is not offered.

**Test-case creation is batched and partially successful by design.** An agent creates every case
for a work item in one pass, and one rejected case must not discard the ones already created. So the
response is per-case:

```jsonc
// 201
{ "created": [ { "title": "Imports a valid file", "externalId": "9103",
                 "url": "https://…", "status": "Design", "linked": true, "error": "" },
               { "title": "Rejects a malformed row", "externalId": "",
                 "error": "Provider rejected 'Rejects a malformed row'" } ],
  "succeeded": 1, "failed": 1 }
```

**A `201` therefore does not mean everything worked.** Read `failed`, or each `error`. A failure that
stops *any* case being attempted — an unroutable ticket, an undecryptable PAT — is a 4xx/5xx instead,
because nothing about it is partial.

**Two invariants on the hub's own copy.** A comment the hub published is appended to the stored
`comments`, and an accepted transition updates the stored `status` — so `GET /tickets/{id}` reflects
a change the hub made itself instead of waiting for the next sync to discover it. The status is
updated **only after the provider accepted the transition**: a rejected transition leaves the stored
status untouched rather than recording a state the provider never reached. (For the same reason, an
adapter that cannot transition now *raises* instead of silently doing nothing.)

**A rejected write is a `502` carrying the provider's own reason** — "No Azure DevOps state matching
'Shipped' on work item 1428", "No Jira transition named 'Done' is available". That reason is the only
actionable part, so it is propagated verbatim rather than replaced with a generic message; agents
should surface it.

Every one of these writes is audited with `source` set to the calling audience, so a comment posted
by QAgent is distinguishable from one posted in the hub UI. These are the first writes an agent
causes to leave the hub for a third party, and the audit row is the only record that it happened.

### Hub-only routes

Built and live, but **not** part of the agent contract — they require the `emehub` audience,
so an agent token is refused. Listed so the surface is not mistaken for undocumented:

`PUT|DELETE /credentials/claude`, `PUT|DELETE /credentials/claude/shared`,
`PUT /credentials/claude/mode`, `POST /credentials/claude/test`,
`GET|POST /credentials/claude/usage` · `POST|PATCH|DELETE /connections`,
`POST /connections/{id}/test`, `GET /connections/{id}/{projects|repos|sprints|work-item-metadata}`
· `POST /projects`, `PATCH /projects/{key}`, `DELETE /projects/{key}`,
`PUT /projects/{key}/config`,
`POST /projects/{key}/repos/{repo}/knowledge/build` · all of `/auth/*`.

`POST …/knowledge/build` is hub-only for a specific reason: it clones a repository, runs a
Claude CLI process for minutes and spends money against the owner's credential
([ADR 0007](adr/0007-knowledge-builds-run-on-the-hub.md)). None of that should be reachable
with an agent's token. It answers `202` with the row already at `indexing`; the caller polls
`GET …/knowledge` until the status settles, and reads `lastError` when it settles on `error`.
Requesting a build that is already running returns the same `indexing` row without starting a
second one. Builds beyond `EMEHUB_KNOWLEDGE_BUILD_CONCURRENCY` queue rather than run.

An agent that builds its own knowledge is unaffected: `PUT …/knowledge` above is still how to
report one, and the hub becoming *a* builder does not make it the only one.

`DELETE /projects/{key}` (issue #64) removes the registry row, its `project_config` — the
encrypted test-account passwords included — every `project_knowledge` row for the key, and
the project's directories in the workspace volume. It is scoped own → shared → **404** like
every other project read, and a shared project additionally needs an admin (a real `403` —
the caller can see the row, they just may not delete it).

**Mirrored work items block the delete rather than being cascaded.** A ticket is the hub's
only record that a work item was ever synced, and the hub cannot restore one without the
connection the project was bound to, so deleting a batch as a side effect of tidying up the
registry destroys more than was asked for. Orphaning them — leaving `project_id` pointing at a
row that no longer exists — is not on the table either. The endpoint answers `409` naming the
count; `DELETE /tickets/{external_id}` is the explicit second step. **Agents are unaffected:
a project an agent has cached simply starts answering 404**, exactly as it would for a key
that never existed.

Two exceptions read by agents with their own audience:
`PUT /credentials/claude/refreshed` (the CLI rotated its token; the hub stays authoritative)
and `POST /credentials/claude/usage`.

---

## 4. Secrets that cross the boundary

Two secrets are unavoidable in the current design, and both deserve an explicit decision
rather than a default.

**Claude credential.** `GET /credentials/claude/resolve` returns credential material the
agent writes to disk and points `CLAUDE_CONFIG_DIR` at. The credential therefore leaves the
hub. Mitigations to implement: response is never cached to disk by the agent in plaintext
beyond the CLI's config dir; the CLI's own token rotation is posted back
(`PUT /credentials/claude/refreshed`) so the hub stays authoritative; the endpoint is
audited on every call.

A **background run** reaches this endpoint with a run-scoped grant rather than an access token
(§2) — the 15-minute token expires long before a run does, and a grant is bound to the hub
session so revocation still applies. That is the only supported way to resolve a credential
outside the 15-minute window; holding the access token past its expiry is not a thing that works.

> Since [ADR 0007](adr/0007-knowledge-builds-run-on-the-hub.md) the hub also materialises a
> Claude credential *for itself*, into a locked-down `CLAUDE_CONFIG_DIR` under
> `EMEHUB_WORKSPACE_DIR`, to run a knowledge build. That does **not** change this section:
> nothing crosses the boundary to an agent. It does mean the workspace volume holds plaintext
> credential material for the duration of a build, and must be treated accordingly.

**Credential metadata gained one field** (issue #63). Every credential metadata payload —
including the one `GET /credentials/claude/resolve` returns alongside the material — now
carries `hasRefreshToken: boolean`, and `status` has a fourth value, `refreshable`.

A Claude OAuth *access* token lives hours, so a real `.credentials.json` is past its
`expiresAt` almost immediately; the refresh token beside it means the CLI renews the access
token on its next run. The hub used to derive `expired` from the timestamp alone, which turned
essentially every stored credential red. It now derives `expired` from the timestamp **only
when there is no refresh token**, and reports `refreshable` otherwise. The authoritative
"this credential does not work" signal is unchanged: the stored `expired` status, set when the
CLI actually rejects it, and it still wins over everything derived.

Both changes are additive — the field is new and the status value is new, so a consumer that
does not know about either keeps working, but one that special-cases `status === "expired"`
should be aware it will now see `refreshable` where it used to see `expired`. **The refresh
token itself is not exposed**: the hub stores only the boolean, and the token stays inside the
encrypted blob that `/resolve` already returns whole.

**Provider PAT.** Deliberately *not* returned. Agents that need a provider call get one of:

- **the hub performs the call through a narrow, purpose-built endpoint** — `POST /tickets/sync`
  today (§3), and this is the preferred answer, not a stopgap;
- the hub performs the call through the generic `POST /connections/{id}/proxy` — **deferred**,
  because a caller-directed forwarder needs its own security design;
- or, where an agent must talk to the provider directly at volume, a scoped short-lived
  token if the provider supports one.

The first and second are the same principle at different widths, and the width is the whole
argument: a narrow endpoint cannot be pointed at an arbitrary upstream, so it carries none of the
SSRF or header-leak risk that deferred the generic one. Prefer adding a narrow endpoint over
reviving the proxy.

**Where this now stands.** Every provider operation QAgent performs is covered by a narrow endpoint:
work-item sync, comment reads, test-case reads, comment publishing, state transitions and test-case
creation. So `/connections` staying informational is no longer what keeps an agent's
`provider_connections` table alive — the remaining work is agent-side, cutting over to these
endpoints and deleting the local table.

Two things are still genuinely uncovered, and both are agent-side by nature rather than blocked here:
**cloning a repository** (the PAT has to be injected into a git remote on the machine doing the
clone) and **anything DAgent hands to an MCP server**, which needs the credential locally by
construction. Those need the scoped-short-lived-token answer, per provider, or nothing.

---

## 5. Degradation

| Hub state | Agent behaviour |
|---|---|
| Reachable | Normal. |
| Unreachable, agent holds a valid unexpired token | Serve cached configuration read-only. Allow work already started to finish. **Refuse** any operation requiring a fresh Claude credential. Show an unmistakable banner. |
| Unreachable, token expired | Refuse. Redirect to the hub login, which will also be down — the error page must say *the hub is down*, not *you are logged out*. |
| Reachable, but the run's **credential grant** expired | Refuse the credential-dependent work, and mint a new grant if the session is live (§2). This is *not* "the hub is down" and *not* "you are logged out" — it is one run running out of authorisation, and it must read as that. |
| Reachable but returns 5xx on a config endpoint | Treat as unreachable for that endpoint only. Do not fall back to an agent-local copy of the same data — that reintroduces the drift the hub exists to remove. |

Explicitly **not** allowed: failing open on authentication. There is no "hub is down so let
everyone in" path.

---

## 6. Known blockers

Recorded now because they are load-bearing, and both live in DAgent
(`ticket-executor/ticket-executor/`).

### 6.1 DAgent's auth gate disables itself

`lib/auth.ts` exposes `authDisabled()`, which returns true when `APP_ACCESS_PASSWORD` is
empty — and `proxy.ts` then lets every request through, pages and API alike. The file is
self-labelled "POC — no user accounts".

This must be **removed**, not supplemented. Adding hub token validation alongside a switch
that turns authentication off entirely leaves the off switch in production. Phase 5 deletes
`authDisabled()`, the `te_session` HMAC cookie and `/api/auth/*`, and replaces the gate in
`proxy.ts` with hub-token validation.

### 6.2 DAgent has no server-side Claude credential

DAgent shells out to whatever `claude` binary is logged in on the host
(`lib/execution/claudeCli.ts`), with `--dangerously-skip-permissions`. There is no
`ANTHROPIC_API_KEY` and no credential store anywhere in the repo.

Consuming a hub-issued credential therefore means building a materialisation path
equivalent to QAgent's `claude_credentials.materialize()` — write the resolved credential to a
per-user `CLAUDE_CONFIG_DIR`, run the CLI against it, capture rotated tokens back to the hub.
Until that exists, DAgent can consume hub *identity* but not hub *credentials*, and those two
milestones should not be bundled into one issue. The hub's own
`api/app/services/claude_credentials.py::materialize` ([ADR 0007](adr/0007-knowledge-builds-run-on-the-hub.md))
is now a second worked example of that path, alongside QAgent's.

Note that [ADR 0007](adr/0007-knowledge-builds-run-on-the-hub.md) removes one thing from
DAgent's critical path: it can obtain a **knowledge base** from the hub today, with no build
capability of its own. That was one of the reasons for the reversal.

Separately: `--dangerously-skip-permissions` is defensible for a single-developer local tool
and indefensible for a multi-user service. Whether DAgent stays local-only or becomes a
hosted service is an open product question that Phase 5 must answer before it starts.

### 6.3 QAgent's secret does double duty

`QAGENT_SECRET_KEY` signs JWTs *and* derives the Fernet key for every encrypted credential
(`api/app/crypto.py`). Moving authentication to the hub while credentials still live in
QAgent would split one secret across two services. See
[ADR 0005](adr/0005-secret-and-key-management.md); the migration is a re-key, not a copy.

---

## Open items

- **Repository ownership.** `emehub` and `q-agent` are under `chuongnd2612`;
  `ticket-executor` is under `DaoLinh98`. The cross-repo delivery rule in
  [CLAUDE.md](../CLAUDE.md) assumes shared access to all three. Consolidating under one
  organisation is unresolved.
- **Organisation entity.** The hub currently plans to inherit QAgent's `owner_id` + `shared`
  convention. Whether to introduce a real organisation/team entity should be settled before
  Phase 2 writes the user schema, because retrofitting it later is a migration across every
  table.
- **DAgent hosting model.** Local developer tool or hosted service? Determines almost
  everything about §6.2.
- **Audit granularity.** Whether agents post individual events or batch them, and how much
  detail crosses the boundary.
