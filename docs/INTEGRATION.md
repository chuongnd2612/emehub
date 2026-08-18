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

**Where the agent is served decides what this needs.** Two supported arrangements:

| Arrangement | `EMEHUB_AGENT_<X>_URL` | Also required |
|---|---|---|
| **Same origin as the hub**, mounted on a path behind the shared front door (ADR 0010) | `/qagent` | nothing — the cookie is already on the origin, so no cookie `Domain` and no CORS entry |
| **Its own host**, a sibling subdomain (ADR 0008) | `https://qagent.example` | `EMEHUB_COOKIE_DOMAIN` set to the shared parent, and the agent's origin in `EMEHUB_CORS_ORIGINS` |

Prefer the first. It is the arrangement with the smallest cookie scope, and `GET /agents` reports
`handoffReady: true` for it without any further configuration.

An agent on an unrelated registrable domain can do neither; that case needs a short-lived
single-use hand-off code redeemed server-to-server, recorded as the fallback in ADR 0008 and not
built.

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
| `GET` | `/connections` | Provider connections visible to the user, with their capabilities (`work_item`, `repository`) and `updatedAt`. Never includes the PAT. |
| `GET` | `/connections/{id}/secret` | **The connection's PAT**, plus the base URL and config that go beside it. Agent audiences only — a hub token is refused. The one place a provider secret crosses; see §4 and [ADR 0010](adr/0010-a-provider-secret-may-cross-to-an-agent.md). |
| `POST` | `/connections/{id}/proxy` | *(never)* A generic forwarder, abandoned rather than deferred. See §4. |
| `GET` | `/projects` | Project registry. Each row carries a `summary` of non-secret card figures (repo, branch, counts, knowledge status) so a list screen costs one request, not 3N+1. **No test-account material, not even `hasPassword`.** |
| `GET` | `/projects/{key}` | One project, same shape as a list row. |
| `GET` | `/projects/{key}/config` | Full project configuration including repositories. Test-account passwords are returned **only to the owning user** — a shared config (`owner_id IS NULL`) is owned by nobody, so its accounts stay masked even for an admin. |
| `GET` | `/projects/{key}/knowledge` | Project-level knowledge. 404 when the project has no knowledge row. |
| `GET` | `/projects/{key}/repos/{repo}/knowledge` | Per-repository knowledge base; falls back to the project-level row. |
| `PATCH` | `/projects/{key}/repos/{repo}/knowledge` | **Write.** Contribute discovered entries (QAgent's runtime selector discovery). Must not clobber existing `verified_at_runtime` entries. |
| `PUT` | `/projects/{key}/repos/{repo}/knowledge` | **Write.** Report the result of a build the agent ran on its own host — status, blob, confidence, and `docPath` (an opaque agent-host path the hub stores and never resolves). |
| `GET` | `/tickets` | Synced tickets, paged and filterable by project, provider, connection, state, assignee, sprint and free text. |
| `GET` | `/tickets/{external_id}` | One ticket, normalised. Optional `?providerKind=` disambiguates the same id across providers. Carries `url` — see *The work item's own URL* below. |
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

**Connections are the one resource with a real invalidation signal.** `updatedAt` is bumped on every
write to a connection, a PAT rotation included, and `GET /connections` returns it. An agent that
mirrors connections compares the value it holds against that list and re-reads
`GET /connections/{id}/secret` only for a row that actually moved — one cheap call, and a secret read
only when there is something new to read. There is deliberately no webhook: a push would need the hub
to reach an agent that may be on a developer's laptop, with retries and ordering, to deliver what one
list call already answers.

### DAgent's provider surface: `/dagent/*`

DAgent drives a coding agent against a work item and then against the pull request that work item
produced. Pull requests have no other consumer in the hub, and DAgent needs work items at a fidelity
the mirrored `tickets` table does not keep (the provider's own rich text, the deep link, the original
estimate and story points). Widening the shared routes to serve that would change endpoints QAgent
and the hub UI already depend on, so these live under their own prefix and are **purely additive** —
a deployment that never calls them behaves exactly as it did before they existed.

All are scoped to one connection the caller owns, and all read live at the provider.

| Method | Path | Returns |
|---|---|---|
| `GET` | `/dagent/connections` | The catalogue, same no-PAT rule as `GET /connections`. |
| `GET` | `/dagent/connections/{id}/projects` | The organisation's projects. |
| `GET` | `/dagent/connections/{id}/sprints?project=` | Iterations plus which one is current, for the **project the caller named**. |
| `GET` | `/dagent/connections/{id}/tickets?project=&sprint=&scope=` | One view's work items, at full fidelity. `scope` is `sprint` (default) \| `backlog` \| `board`. |
| `GET` | `/dagent/connections/{id}/tickets/{ext}/comments` | The work item's comment thread. `{items, supported}`. |
| `GET` | `/dagent/connections/{id}/tickets/{ext}/states` | The states **this work item type** may hold — not the union across the project. |
| `GET` · `POST` | `/dagent/connections/{id}/tickets/{ext}/status` | Read the current state; **write** a transition. |
| `GET` | `/dagent/connections/{id}/pull-request` | The PR linked to a work item, and its review threads. `pr: null` means nothing is linked — a real answer. |
| `POST` | `/dagent/connections/{id}/pull-request/review-summaries` | The same question for **many** work items at once, answered with a count and the newest open comment rather than whole threads. See below. |
| `GET` | `/dagent/connections/{id}/pull-request/commits` | Every commit on the PR's source branch. |
| `GET` | `/dagent/connections/{id}/pull-request/commits/{sha}` | One commit's file changes, each with a unified diff. |
| `POST` | `/dagent/connections/{id}/pull-request/outcomes` | What became of a batch of PRs — merged, abandoned, review-comment count. |

**`project` is a caller argument on both work-item reads, and that is load-bearing.** One connection
spans a whole organisation while DAgent picks a project in its own header, so a route that resolved the
project from `connection.config` answers for whichever project the connection happens to name — and for
nothing at all when it names none. `sprints` used to do exactly that, which left DAgent's sprint picker
empty while the ticket list beside it, which does send a project, kept working: a picker that silently
disagreed with the list it sat next to. `sprints` is therefore served from `dagent_provider`, not from
the shared adapter, whose own `list_sprints()` still reads the connection's project for the hub UI.

**A sprint list is scoped to a team, not to a project.** `/sprints` reads `work/teamsettings/iterations`
under the project's **default team** — the same context `@currentIteration` resolves through, so the
picker's default and a no-sprint ticket load agree. It deliberately does *not* read the project's
classification tree: that is every iteration the project has ever defined across every team's sub-tree,
and a project of any age answers with a soup (`CPCAG Sprint 75` beside `FM-Schwab-Egnyte\Sprint 8` beside
`Sprint 47`) matching no screen a user has seen, since ADO's own sprint URL is `_sprints/backlog/<team>/…`.
It also made "current" unanswerable: several of those sub-trees have a sprint spanning today, so a date
comparison matched more than one. Team settings returns ADO's own `attributes.timeFrame`, so exactly one
item is `current`, and `current` at the top level names it.

**`sprint` is an iteration *path*, and `/sprints` hands you one.** `System.IterationPath` is rooted —
`RIS\Sprint 61`, or `RIS\Release 1\Sprint 61` where iterations nest — and ADO does not treat a bare leaf
name as a filter that matches nothing: it rejects the whole query with a `400`, which reaches the caller
as a `502` about WIQL it never wrote. So pass back the `path` from `/sprints`, not the `name` the picker
displayed. A bare name is still accepted and resolved against the project's iterations first, at the cost
of one extra call; a name that matches no iteration falls back to `project\name`, which is right for a
flat layout and leaves an unknown sprint as an empty list rather than an error. The `sprint` echoed in
the response is always the **leaf**, because a header chip is a name and a path is a location.

**The three `scope`s are three queries, not one query with a filter.** A sprint is bounded by its
iteration and keeps its closed work — it is the record of what that iteration did. A backlog is open
work whose iteration path is still the project root, i.e. not scheduled yet. A board is every open work
item *regardless* of iteration, carrying `boardColumn` — the kanban column, which is not the state,
because a board maps several states onto one column and may add custom ones. Two of the three
deliberately sit outside the iteration the sprint query is bounded by, so no caller can derive them
from a sprint fetch. An unrecognised `scope` is a `422` rather than a silent fall back to `sprint`:
answering a question nobody asked is how a caller ends up trusting the wrong list. Both non-sprint
scopes answer with an empty `sprint` label, since naming one iteration for a list that spans them all
would be false, and every scope reports `truncated` when the provider had more than `MAX_TICKETS` to
give — a sprint is bounded, a backlog and a board are not, and a capped list that says nothing reads as
a short one.

The two `POST`s that take a list are POSTs because a board's worth of ids does not fit a query string,
not because they write anything. **Neither turns a caller's string into an upstream address**: a PR URL
is parsed for a repository and PR id, and the request is then built from the connection's own base
URL — which is what keeps these from being the generic forwarder §4 rules out.

`review-summaries` exists because polling is not free. A notification bell asks about every ticket on
screen on a timer; doing that through the single-ticket route cost one round-trip *and* one full review
payload per ticket per poll, nearly all of it discarded on arrival. The batch form answers
positionally, with `null` where there is nothing to notify about — and per §5, a batch that could not
be read at all is a `502`, never a list of nulls, because an outage and an empty board must not render
the same.

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

### The detail payload's nested shapes

`GET /tickets/{external_id}` carries three lists the list endpoint does not, and each one now has
a declared item shape rather than being an untyped array:

| Field | Items |
|---|---|
| `comments` | `{who, when, text}` — the snapshot as of `syncedAt`. Identical to the live read above. |
| `attachments` | `{name, size}`. `size` is the provider's own string, unparsed: Jira gives bytes, Azure DevOps gives nothing, and turning the two into a number would invent precision neither offers. |
| `linkedPrs` | `{repo, num, title, status, url}`. `num` is a string — GitHub numbers and Azure DevOps ids are not the same kind of thing. |

**Every field is optional and defaults to `""`.** These dicts were written by provider adapters
over time, so a stored row missing a key normalises to an empty string rather than failing the
read — a detail request must not 500 over a field the caller does not even display. Unknown keys
are dropped. The typing is documentation plus a normalisation floor, not a validation gate.

`acceptanceCriteria` (a `string[]`) and `acceptanceCriteriaHtml` stay as they were: the split list
when the provider's criteria divide cleanly, and the provider's original HTML alongside it for when
they do not. Render the list when it has two or more entries and fall back to the HTML otherwise —
and **sanitize the HTML**, because it is the provider's, not the hub's.

### The work item's own URL

Every ticket the hub returns — list, detail, preview sample and sync result alike — carries a
**`url`**: the work item's page in the provider. Azure DevOps gives
`{org}/{project}/_workitems/edit/{id}`, Jira gives `{base}/browse/{key}`, GitHub gives the issue's
`html_url`. Provider-side test cases (`GET …/test-cases`) carry one too.

It exists so that **sending a human back to the source never requires a provider connection**. An
agent that wants to put "open the work item" in a comment, a report or a UI would otherwise have to
hold the org URL and reconstruct the path per provider — which means knowing each provider's URL
grammar, and getting it wrong for on-premises Azure DevOps and Jira Data Center, where the base is
not guessable. The hub already knows the base, because the connection it synced through told it.

`""` means **the hub has no link to offer**, not that the link is broken: an adapter without an org
or base URL configured cannot build one. Render a link only when the field is non-empty, and never
construct a fallback — a wrong deep link is worse than no deep link.

Additive and defaulted, so a consumer that ignores it is unaffected. Existing rows read `""` until
their next sync fills them; nothing is backfilled from the provider, because a sync is the only
place the hub is entitled to make that call.

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
agent writes to disk and points **`CLAUDE_SECURESTORAGE_CONFIG_DIR`** at. The credential
therefore leaves the hub. Mitigations to implement: response is never cached to disk by the
agent in plaintext beyond that directory; the CLI's own token rotation is posted back
(`PUT /credentials/claude/refreshed`) so the hub stays authoritative; the endpoint is
audited on every call.

> **Not `CLAUDE_CONFIG_DIR`.** The CLI resolves the credential file from
> `CLAUDE_SECURESTORAGE_CONFIG_DIR ?? CLAUDE_CONFIG_DIR ?? ~/.claude`, but `skills/`,
> `settings.json` and `projects/` from `CLAUDE_CONFIG_DIR ?? ~/.claude` (verified against
> claude 2.1.226). An agent that sets the wide variable to a directory holding only a
> credential loses its own skills with it: DAgent did exactly that and every run failed at
> its first node with `Unknown command: /implement-ticket-v3`, the slash-command table
> having dropped from 125 entries to 42. The narrow variable moves the credential alone.
> An agent must also never write into the host's own `~/.claude` — that is the developer's
> login, and for a `shared` credential it would sign them in as somebody else.
>
> The hub's own knowledge build is the one place `CLAUDE_CONFIG_DIR` is still correct: it
> runs in a container, wants the whole root isolated, and passes its skill as
> `--append-system-prompt` rather than a slash command, so it depends on no installed skills.

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

**Provider PAT.** Not returned *by default*, and returned by exactly one endpoint. An agent that
needs a provider operation gets one of, in order of preference:

- **the hub performs the call through a narrow, purpose-built endpoint** — `POST /tickets/sync` and
  the `/tickets/{external_id}/…` reads and writes (§3). This is the preferred answer, not a stopgap:
  the caller names a *ticket*, never a URL, so the secret never has to move;
- or, where the provider supports one, a scoped short-lived token the agent holds itself. GitHub
  installation tokens qualify; classic Azure DevOps and Jira PATs have no equivalent;
- or, **only where neither is possible**, `GET /connections/{id}/secret`.

`POST /connections/{id}/proxy` — a generic, caller-directed forwarder — is **abandoned, not
deferred**. It is an SSRF and header-leak surface, and the narrow endpoints cover every provider
call an agent's own code makes. Prefer adding a narrow endpoint; never revive the proxy.

**Where this now stands.** Every provider operation QAgent performs is covered by a narrow endpoint:
work-item sync, comment reads, test-case reads, comment publishing, state transitions and test-case
creation. The remaining work there is agent-side — cutting over and deleting the local table.

**Two cases have no seam to insert a hub call into, and that is why the third bullet exists**
([ADR 0010](adr/0010-a-provider-secret-may-cross-to-an-agent.md)). **Cloning a repository** needs the
PAT in a git remote on the machine doing the clone. **Anything DAgent hands to an MCP server** needs
it in a subprocess's environment — DAgent writes a config file, the Claude CLI starts
`@azure-devops/mcp` from it, and *that* process calls the provider. Neither is a call the hub can
make on the agent's behalf, so for these the credential crosses.

An agent that reads it takes on three obligations:

- **store it where a credential belongs** — encrypted at rest, never in a log, never in a response;
- **treat the hub as the place it is edited.** The agent's copy is a mirror keyed on `updatedAt`
  (§3), not a second editable source. An agent that lets a user edit a mirrored connection
  re-creates exactly the drift the hub exists to remove;
- **fail closed.** An unreadable or undecryptable credential is a refusal, not an empty string
  passed on to the provider — §5, one level down.

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

Recorded now because they are load-bearing, and they live in DAgent
(`ticket-executor/ticket-executor/`). 6.2 is closed and kept for the record, since the
mistake it ends on is the one another agent is most likely to repeat.

### 6.1 DAgent's auth gate disables itself

`lib/auth.ts` exposes `authDisabled()`, which returns true when `APP_ACCESS_PASSWORD` is
empty — and `proxy.ts` then lets every request through, pages and API alike. The file is
self-labelled "POC — no user accounts".

This must be **removed**, not supplemented. Adding hub token validation alongside a switch
that turns authentication off entirely leaves the off switch in production. Phase 5 deletes
`authDisabled()`, the `te_session` HMAC cookie and `/api/auth/*`, and replaces the gate in
`proxy.ts` with hub-token validation.

### 6.2 DAgent has no server-side Claude credential — **closed**

DAgent now has the materialisation path this entry asked for, in `lib/claudeConfig.ts` and
`lib/hubCredential.ts`: with hub mode on, `startRun()` resolves the credential
(`GET /credentials/claude/resolve`, with the access token — admission runs before a run id
exists, so before a grant can be minted), writes it under
`~/.ticket-executor/claude-config/<own|shared>/`, points
`CLAUDE_SECURESTORAGE_CONFIG_DIR` there for every turn, and after each turn posts back the
rotated token (`PUT …/refreshed`) and the spend (`POST …/usage`) with a run-scoped grant.
It does **not** fall back to the host's login: no credential is an admission refusal,
recorded before the run row exists so it is not counted as an agent failure.

With hub mode **off** the original behaviour is untouched — the CLI is spawned with an
unmodified environment and uses whatever `claude` login the host has.

Read the box in §4 before porting this to another agent: the env var is the narrow one, and
the wide one silently costs the agent its own skills.

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
