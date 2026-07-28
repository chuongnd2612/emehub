# EmeHub — Integration contract

The specification QAgent and DAgent implement in order to be part of the suite. Written
before any code so it can be argued with cheaply.

Status: **draft, nothing implemented.** Every endpoint below is a target, not a promise.

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
| `GET` | `/projects` | Project registry: key, name, base URL, environments, bound connections. |
| `GET` | `/projects/{key}/config` | Full project configuration including repositories. Test-account passwords are returned only to the owning user. |
| `GET` | `/projects/{key}/knowledge` | Project-level knowledge. |
| `GET` | `/projects/{key}/repos/{repo}/knowledge` | Per-repository knowledge base. |
| `PATCH` | `/projects/{key}/repos/{repo}/knowledge` | **Write.** Contribute discovered entries (QAgent's runtime selector discovery). Must not clobber existing `verified_at_runtime` entries. |
| `GET` | `/tickets` | Synced tickets, paged and filterable by project. |
| `GET` | `/tickets/{external_id}` | One ticket, normalised. |
| `POST` | `/audit/events` | **Write.** Append an audit event attributed to the calling agent. |

Agents MAY cache any `GET` above. Cache lifetime is the agent's choice; the hub sets
`Cache-Control` as a hint, not a rule.

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
milestones should not be bundled into one issue.

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
