# EmeHub — Integration contract

The specification QAgent and DAgent implement in order to be part of the suite.

Status: **the hub side is built; no agent consumes it yet.** Everything in §2 and §3 is live
against the running API — you can call it today. What has *not* happened is the other half:
neither QAgent nor DAgent validates a hub token or reads its configuration from here, so the
hub currently runs in parallel with both rather than in front of them. See
[ROADMAP.md](ROADMAP.md) Phases 2–5.

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
| `POST` | `/audit/events` | **Write.** Append an audit event attributed to the calling agent. |

Agents MAY cache any `GET` above. Cache lifetime is the agent's choice; the hub sets
`Cache-Control` as a hint, not a rule.

### Hub-only routes

Built and live, but **not** part of the agent contract — they require the `emehub` audience,
so an agent token is refused. Listed so the surface is not mistaken for undocumented:

`PUT|DELETE /credentials/claude`, `PUT|DELETE /credentials/claude/shared`,
`PUT /credentials/claude/mode`, `POST /credentials/claude/test`,
`GET|POST /credentials/claude/usage` · `POST|PATCH|DELETE /connections`,
`POST /connections/{id}/test`, `GET /connections/{id}/{projects|repos|sprints|work-item-metadata}`
· `POST /projects`, `PATCH /projects/{key}`, `DELETE /projects/{key}`,
`PUT /projects/{key}/config`,
`POST /projects/{key}/repos/{repo}/knowledge/build` ·
`POST /tickets/sync`, `DELETE /tickets/{external_id}` · all of `/auth/*`.

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

- the hub performs the call (`POST /connections/{id}/proxy`) — preferred, PAT never leaves;
- or, where an agent must talk to the provider directly at volume, a scoped short-lived
  token if the provider supports one.

Phase 3 will pick one per provider rather than one globally. Until then agents keep their own
provider credentials and the hub's `/connections` is informational.

---

## 5. Degradation

| Hub state | Agent behaviour |
|---|---|
| Reachable | Normal. |
| Unreachable, agent holds a valid unexpired token | Serve cached configuration read-only. Allow work already started to finish. **Refuse** any operation requiring a fresh Claude credential. Show an unmistakable banner. |
| Unreachable, token expired | Refuse. Redirect to the hub login, which will also be down — the error page must say *the hub is down*, not *you are logged out*. |
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
