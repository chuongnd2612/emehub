# EmeHub → QAgent launch and SSO hand-off — implementation plan

> Scope of this document: making "Launch QAgent" real, so signing in at the hub signs you in at
> the agent. It is the **agent cutover half of [ROADMAP](ROADMAP.md) Phase 2**, for one agent.
> Paths without a repo prefix are in this repository; Q-Agent paths are marked `q-agent/`.

## Status

| Track | State |
|---|---|
| **A — EmeHub** | **Done.** A1 `POST /auth/agent-token` (#75) · A2 CORS + cookie-domain config (#77) · A3 `GET /agents` (#79) · A4 the Launch buttons (#81) · A5 ADR 0008 and these docs. |
| **B — Q-Agent** | Not started. Tracked in [q-agent#476](https://github.com/chuongnd2612/q-agent/issues/476), planned in `q-agent/docs/HUB-INTEGRATION.md`. |
| **DAgent** | Deferred — §5. Prerequisites filed as [ticket-executor#81](https://github.com/DaoLinh98/ticket-executor/issues/81). |

**One decision changed during implementation.** §1 below is written as designed and remains
accurate: the mechanism is the shared cookie plus a **non-rotating** mint. The plan originally
considered having the agent call `/auth/refresh` directly; that was rejected once it was confirmed
that `/auth/refresh` rotates (`api/app/services/auth_service.py:333-344`), which makes two SPAs
sharing one cookie race and log each other out.

**To enable it on a deployment**, set on the hub: `EMEHUB_COOKIE_DOMAIN` to the shared parent
domain, `EMEHUB_COOKIE_SECURE=true`, `EMEHUB_CORS_ORIGINS` to include the agent's origin, and
`EMEHUB_AGENT_QAGENT_URL` to the agent's deployed origin. Until then `GET /agents` reports
`handoffReady: false` with reason `no_cookie_domain`, and the UI disables launching rather than
offering a click that fails.

## Context

The hub is built and running — identity, Claude credentials, provider connections, projects,
knowledge (which it now builds itself, [ADR 0007](adr/0007-knowledge-builds-run-on-the-hub.md)),
tickets and audit, with ~408 backend tests and all eleven designed views on real endpoints.

What does **not** exist is any way to get from the hub into an agent. Both "Launch" affordances are
literal no-ops:

- `app/src/screens/Overview/ProductCard.tsx:63` — `// NO-OP: neither agent has a destination in
  the route map yet` followed by `onClick={() => {}}`
- `app/src/screens/Landing/ProductCard.tsx:22-36` — fires a toast and navigates nowhere

`api/app/config.py:67-68` already holds `agent_qagent_url` / `agent_dagent_url`, but
`registered_audiences` uses them **only as feature flags** deciding which JWT audiences to mint.
No endpoint exposes them to the frontend, so `.env.example:53` ("and where the UI links each
agent") is doc drift.

Meanwhile Q-Agent has **zero** references to the hub in tracked code, and [ROADMAP](ROADMAP.md)
records Phases 2–4 as "hub side done, **agent cutover not started**". So the hub runs *alongside*
Q-Agent rather than in front of it — precisely the outcome
[ADR 0001](adr/0001-emehub-is-the-source-of-truth.md) rejected when it ruled out the
"launcher / portal" option as "cheap; solves nothing".

**Intended outcome.** Sign in once at `hub.chuongnd.click`, click Launch QAgent, land at
`qagent.chuongnd.click` already authenticated. Q-Agent keeps its own login working alongside, so
nothing breaks in one step.

## Decisions taken

| Decision | Choice |
|---|---|
| Hosting | Subdomains of one registrable domain via cloudflared: `hub.chuongnd.click`, `qagent.chuongnd.click`, … |
| Scope | Hub → QAgent real SSO. Q-Agent's local `/auth/*` stays working alongside. |
| Hand-off payload | Identity only; lands on the agent's home. No context deep-link. |
| Mechanism | Shared refresh cookie on `.chuongnd.click` + a **non-rotating** audience-token mint. |
| DAgent | Deferred; make its card honest. |

---

## 1. Mechanism: shared cookie + non-rotating mint

```
1. User logs in at hub.chuongnd.click
     emehub_refresh (Domain=.chuongnd.click, Secure, HttpOnly, SameSite=Lax)
     emehub_csrf    (Domain=.chuongnd.click, readable — double-submit)

2. Overview "Launch QAgent" → top-level navigation to https://qagent.chuongnd.click/

3. QAgent SPA boots, finds no local session, and calls the hub cross-origin:
     POST https://hub.chuongnd.click/auth/agent-token   { audience: "qagent" }
     credentials: 'include', X-CSRF header read from emehub_csrf
     → { accessToken (aud=qagent), user, expiresIn }

4. QAgent posts that token to its own POST /auth/sso/complete, which verifies it and
   creates a NORMAL QAgent refresh session → redirect to /
```

The two subdomains share one registrable domain, so they are **same-site**: a
`Domain=.chuongnd.click` cookie with `SameSite=Lax` is sent on cross-origin XHR from the agent's
origin, and `api/app/main.py:166-173` already configures `CORSMiddleware` with
`allow_credentials=True` and an origin allowlist.

### Why a new endpoint rather than `/auth/refresh`

`POST /auth/refresh` **rotates** the refresh token — `api/app/services/auth_service.py:333-344`
overwrites `refresh_token_hash`, and `find_session_by_refresh` is an exact hash lookup, so the old
value dies instantly. If the hub SPA and Q-Agent both refreshed using the same shared cookie,
concurrent silent refreshes would race and whichever lost would be logged out of a session it
legitimately held. Intermittent, and user-visible.

`POST /auth/agent-token` sidesteps this entirely by **not rotating**: it reads the cookie, mints one
audience token, and leaves the refresh token untouched. The hub's own `/auth/refresh` path keeps
rotating, unchanged.

### Why the hub token is used exactly once

Step 4 creates a Q-Agent-native session, so the hub access token is consumed at bootstrap and
discarded. This slice therefore has **no 15-minute token problem and needs no agent-side refresh
mechanism**. That only becomes necessary when Q-Agent starts *reading* hub config (Phases 3–4 — see
§6). Do not build it here.

### Accepted trade-offs

To be recorded in ADR 0008, not left implicit:

- **Subdomain trust is load-bearing.** XSS on any `*.chuongnd.click` page can call
  `/auth/agent-token` and mint agent tokens. `verify_csrf`
  (`api/app/services/auth_service.py:408-412`) is a plain double-submit against a *readable*
  cookie, which any subdomain can read — so it offers no protection against a same-site attacker.
  Accepted because every subdomain is self-hosted and operated by one small team. **Revisit if the
  suite moves to a domain where other people operate subdomains.**
- **Locked to one registrable domain.** If an agent ever moves off `chuongnd.click`, cookie sharing
  stops working. The fallback is a short-lived single-use hand-off code redeemed server-to-server
  with a per-agent client secret — documented as the migration path, not built.
- **Slightly weaker refresh-token reuse detection**, since one path now accepts the refresh token
  without rotating it. Mitigate by auditing every `/auth/agent-token` call (user, audience, IP).
- Revocation latency is the access token's 15 minutes, which [INTEGRATION §2](INTEGRATION.md#2-token)
  already accepts.

### Constraints found in the code

- The hub has **no auth off switch by design** (`api/app/security.py:17-21` — "no
  `EMEHUB_AUTH_REQUIRED`, no `authDisabled()`"). Do not add one.
- **`PUBLIC_PATHS` is matched exactly, never by prefix** (`api/app/security.py:23-25`).
  `/auth/agent-token` must be a literal entry — it authenticates by refresh cookie, not by bearer
  token, so the user-token guard would otherwise reject it. `/auth/refresh` is already listed for
  the same reason, so this follows an established pattern rather than creating an exception.
- Q-Agent's access tokens carry `{sub, role, sid, typ:"access"}` — **no `iss`, no `aud`** — while
  hub tokens carry `iss`/`aud` and no `typ`. A dual-accept decoder can discriminate cleanly on
  `iss`, with no ambiguity.
- Q-Agent's refresh cookie is scoped `path="/auth"` with no domain, and `q-agent/app/nginx.conf`
  proxies `/auth/` unrewritten with `/` → `index.html` fallback. So a new `/sso/callback` SPA route
  and a new `POST /auth/sso/complete` backend route need **zero nginx changes**.
- The login/refresh response shape is `{ accessToken, tokens: dict[audience → token], expiresIn,
  user }` (`api/app/schemas.py:71-118`). `audiences` is on the *request*, not the response.

---

## 2. Track A — EmeHub

### A1 · `POST /auth/agent-token` — solo foundation

In `api/app/routers/auth.py`, next to `refresh` so the two stay visibly related:

1. read the refresh cookie; 401 if missing
2. `verify_csrf` against the `X-CSRF` header; 403 on mismatch
3. `find_session_by_refresh`; 401 if the session is dead or the user is inactive
4. reject an audience not in `registered_audiences`, and reject `emehub` itself — this endpoint
   exists for agents; the hub's own SPA uses `/auth/refresh`
5. mint **only** that audience's token through the existing minting path; update `last_seen_at`
6. **do not call `auth_service.rotate`** and do not re-issue cookies
7. audit the call

Add `"/auth/agent-token"` to `PUBLIC_PATHS` with a comment explaining it is cookie-authenticated,
not unauthenticated.

**Tests:** happy path · `emehub` audience refused · unregistered audience refused · missing and
mismatched CSRF · revoked session · inactive user · **and an explicit assertion that the refresh
token hash is byte-identical after the call.** That last assertion is the entire design; it must be
pinned by a test, not by a comment.

### A2 · Config and deployment — parallel with A1

- `EMEHUB_COOKIE_DOMAIN=.chuongnd.click`
- `EMEHUB_COOKIE_SECURE=true`
- `cors_origins` (`api/app/config.py:117`) extended with `https://hub.chuongnd.click` and
  `https://qagent.chuongnd.click`

Update `.env.example` and `docker-compose.yml`. While there, fix two pieces of drift: the `:53`
comment claiming the agent URLs are "where the UI links each agent" (true only after A3/A4), and
the `:47-49` cookie-domain note, which stops being hypothetical and becomes real guidance.

### A3 · `GET /agents` — after A2

New `api/app/routers/agents.py`, registered in `main.ROUTERS` with posture **`PROTECTED`**
(`aud: emehub` only — an agent has no business reading the registry).

Deliberately **not** added to `GET /me`, which is a documented agent-contract endpoint returning
"exactly `id, email, name, role`"; the registry has nothing to do with the calling principal, and
changing `/me` would ship a contract change for a UI convenience.

```json
{ "agents": [
  { "id": "qagent", "key": "q", "name": "Q-Agent",
    "url": "https://qagent.chuongnd.click",
    "registered": true,  "handoffReady": true,  "reason": null },
  { "id": "dagent", "key": "d", "name": "D-Agent",
    "url": null,
    "registered": false, "handoffReady": false, "reason": "no_url" }
] }
```

Add `Settings.handoff_ready(audience)` so that "a URL is set" cannot silently mean "SSO works".

### A4 · Frontend — file-disjoint from A1–A3, runs in parallel

Coded against A3's documented shape.

- `app/src/data/agents.ts` plus `AgentTarget` in `app/src/data/types.ts`, exported through the
  `app/src/data/index.ts` barrel — screens import from `@/data` only, a rule stated in the barrel's
  own header.
- `app/src/data/overview.ts::getProducts()` merges the registry into the static `PRODUCTS` copy.
  **`live` stays static** — it drives the "Live"/"Placeholder" pill, which is binding design copy,
  not runtime state.
- `app/src/screens/Overview/ProductCard.tsx` — replace the no-op with three honest states:
  - `handoffReady` → real launch via `window.location.assign(url)`, a top-level navigation rather
    than a new tab
  - `registered && !handoffReady` → disabled, with a tooltip naming the missing configuration
  - `!registered` → today's placeholder path
- `app/src/screens/Landing/ProductCard.tsx` is **public**, and `GET /agents` requires auth — so it
  must not call it. Replace the toast with navigation to `/app`, letting the existing `RequireAuth`
  either restore the session (→ Overview, where the real Launch lives) or bounce to `/login`.
- **A4 also carries the honest DAgent card** (§5). Same files, so do not file it separately.

### A5 · Documentation

- `docs/adr/0008-cross-app-session-handoff.md` — the shared-cookie decision, the rotation race that
  forced a separate non-rotating endpoint, the accepted subdomain-trust trade-off, and the
  single-use-code flow as the documented migration path.
- [INTEGRATION.md](INTEGRATION.md) — §2 gains the mint endpoint; §5 gains the degradation rows
  from §3 below.
- [ROADMAP.md](ROADMAP.md) — Phase 2 agent-cutover status.

---

## 3. Track B — Q-Agent (`q-agent/`)

### B1 · Foundation — solo

- `q-agent/api/app/services/hub_tokens.py::decode()` — HS256 against `QAGENT_HUB_JWT_SECRET`,
  `issuer="emehub"`, `audience="qagent"`, requiring `exp/iat/iss/aud/sub`. Mirror
  `api/app/services/auth_service.py::_decode` exactly so the two cannot drift. Read the `kid`
  header and log it, but **do not** key verification on it — that keeps the Phase-3 RS256/JWKS
  switch additive.
- `q-agent/api/app/config.py`: `QAGENT_HUB_BASE_URL`, `QAGENT_HUB_JWT_SECRET`,
  `QAGENT_HUB_AUDIENCE` (default `qagent`), `QAGENT_HUB_SSO_ENABLED` (default **false**).
  A separate secret from `QAGENT_SECRET_KEY`, which already signs local JWTs *and* derives the
  Fernet key ([INTEGRATION §6.3](INTEGRATION.md#63-qagents-secret-does-double-duty)) — see
  [ADR 0005](adr/0005-secret-and-key-management.md). **No client secret is needed** under this
  mechanism.
- Migration: `users.hub_user_id`, nullable and unique.

**Why the mapping column is load-bearing.** The hub's `sub` is a *hub* user id; Q-Agent's is a
*Q-Agent* user id. They will never match. Nearly every Q-Agent table hangs off `owner_id` →
`users.id`, including the per-user workspace filesystem (`api/workspace/users/<owner_id>/…`,
[ADR 0009 in q-agent]). `hub_user_id` is what lets every existing row keep working with no data
migration in this slice.

### B2 · Dual-accept token validation — parallel with B3

`q-agent/api/app/deps_auth.py` — try the local decoder first, then `hub_tokens.decode`,
discriminating on `iss`. A hub token resolves the local `User` by `hub_user_id`,
**JIT-provisioning** on first sight from `sub` / `email` / `role`.

Two traps:

- `require_user` stashes `user._sid`, and the session routes use it. A hub `sid` is **not** a
  Q-Agent session id — guard those routes so they never try to revoke a hub sid locally.
- The WebSocket paths (`/ws/runs/{run_id}`, `/ws/ai`) validate tokens through their own helper in
  `q-agent/api/app/main.py`. Route them through the same dual-accept path, or hub-token holders
  silently lose live run progress — a failure that surfaces only at runtime.

### B3 · The bootstrap round trip — parallel with B2

- `POST /auth/sso/complete { hubToken, next? }` — verify via `hub_tokens.decode`, map or provision
  the user, create a **normal Q-Agent refresh session**, and return the same body `/auth/login`
  returns.
- `q-agent/app/src/screens/auth/SsoCallback.tsx` plus a route in `q-agent/app/src/router.tsx`,
  registered as a **top-level ungated sibling** like `signed-out` — *not* under `RedirectIfAuthed`
  (which would bounce a returning user mid-bootstrap) and not under `RequireAuth` (the whole point
  is arriving anonymous). On mount: `POST {hubUrl}/auth/agent-token` with `credentials:'include'`
  and the CSRF header, hand the token to `/auth/sso/complete`, then navigate.
- Entry point: with `QAGENT_HUB_SSO_ENABLED`, an unauthenticated load redirects to `/sso/callback`
  once — guard against a loop with a one-shot marker — before falling through to `/login`.

**Shaping the response like a login is the sequencing trick.** It leaves
`q-agent/app/src/store/auth.ts`, `q-agent/app/src/lib/api.ts`'s 401→refresh, and
`RequireAuth.tsx` **completely untouched**: one new screen, no store surgery, and Q-Agent's own
refresh cookie remains the browser-session credential throughout the transition.

### B4 · "Sign in with EmeHub" on `/login` — after B3

Shares `q-agent/app/src/screens/auth/`, so sequenced after B3. Shown only when the backend reports
SSO enabled. Local email + password stays working underneath; purely additive.

### B5 · Degradation

Per [INTEGRATION §5](INTEGRATION.md#5-degradation). Today `q-agent/app/src/lib/api.ts` collapses
transport failure and auth failure into one logout path. Split it:

| Hub response | Meaning | Behaviour |
|---|---|---|
| Refused / DNS / timeout / 502-504 | **The hub is down** | "EmeHub is unreachable — we can't sign you in right now" + Retry. **Never** the login form, never "session expired". |
| 401 (no or dead refresh cookie) | Not signed in at the hub | Fall through to Q-Agent's own `/login`. Not an error. |
| 403 (CSRF mismatch) | Stale hub session state | Prompt to re-sign-in at the hub. |
| 400 unregistered audience | Misconfiguration | Operator-facing error naming `EMEHUB_AGENT_QAGENT_URL`. |
| 401 on a hub read with a valid-looking token | Session revoked at the hub | **This** is "you are logged out." |

No branch anywhere grants access because the hub was unavailable.

---

## 4. Sequencing and parallelism

`{A1 ∥ A2} → A3`, with `A4` and `A5` fully parallel. In the other repo, `B1 → {B2 ∥ B3} → B4`.
The two tracks run concurrently once A1's request/response shape is agreed.

Each repo's own `CLAUDE.md` issue-driven workflow applies: one issue per slice, branch
`feature/<issue-number>`, PR squash-merged with `--admin --delete-branch`, and the Docker image
rebuilt after shipping (`docker compose up -d --build`) — the running container is stale until then.

---

## 5. DAgent: deferred

Not in scope, for four independent reasons, any one of which is sufficient:

1. **No user identity at all.** `ticket-executor/lib/auth.ts` sets `te_session` =
   `HMAC-SHA256(APP_ACCESS_PASSWORD, "authenticated")` — no user records, no subject, nothing that
   can receive a hub identity. Hub SSO into DAgent is not "validate a token", it is "invent a user
   model".
2. **`authDisabled()` fails open** when `APP_ACCESS_PASSWORD` is empty, and `proxy.ts` then lets
   every request through — pages and API alike. [INTEGRATION §6.1](INTEGRATION.md#61-dagents-auth-gate-disables-itself)
   says remove, not supplement.
3. **No containerisation.** No Dockerfile, no compose file, no nginx config, no CI — so it cannot
   sit behind the tunnel as-is. Its gate is `npx tsc --noEmit` only.
4. **Different GitHub account** (`DaoLinh98/ticket-executor` vs `chuongnd2612` for the other two),
   which is the unresolved open item in [INTEGRATION](INTEGRATION.md#open-items).

Plus the product question [ROADMAP](ROADMAP.md) says **gates the whole phase**: is DAgent a local
developer tool or a hosted service? Its `--dangerously-skip-permissions` execution model makes the
answer load-bearing.

**Minimum to make the card honest now** — all in this repo, no `ticket-executor` edits:

- `handoff_ready("dagent")` is false, so `GET /agents` reports
  `{registered: …, handoffReady: false, reason: "no_url" | "no_secret"}`.
- The Overview card renders the existing "Preview" affordance, disabled, with a tooltip saying it
  is not connected. No dead click, no lying toast.
- **Change `EMEHUB_AGENT_DAGENT_URL`'s default to empty.** It currently ships as
  `http://localhost:3000`, which means the hub mints a `dagent` audience token on **every login**
  that nothing on earth validates. Cheap fix, and it makes `registered_audiences` mean what its
  docstring says.
- One issue on `ticket-executor` — "Phase 5 prerequisite: introduce a user model and delete
  `authDisabled()`" — if cross-account access permits. If it does not, **say so** rather than
  silently skipping step 2 of the cross-repo delivery rule.

---

## 6. Shared-config gaps

Found while planning this work. None of them block this slice, but each blocks Phases 3–5 **as
currently written**, so they are recorded here rather than rediscovered later.

**6.1 · The provider PAT never crosses.** `GET /connections` returns `hasPat` and nothing more, and
the intended escape hatch `POST /connections/{id}/proxy` is deliberately unbuilt
(`api/app/routers/connections.py:43`). So Phase 3's exit criteria — "QAgent's
`provider_connections` tables are gone" — is **unreachable**. The Azure DevOps PAT, the motivating
example in [ADR 0001](adr/0001-emehub-is-the-source-of-truth.md) ("a user configures their Azure
DevOps PAT twice"), is still configured twice. Phase 3 needs either the proxy designed or
per-provider scoped tokens chosen.

**6.2 · 15-minute tokens versus 20-minute work.** No service or machine token exists anywhere in
the hub, agents may not refresh ([INTEGRATION §2](INTEGRATION.md#2-token)), yet Q-Agent's AI
pipeline runs in background daemon threads with `QAGENT_CLAUDE_BOOTSTRAP_TIMEOUT_S` alone at 1200s.
A run that needs a fresh Claude credential after minute 15 has no legal path, and §5 forbids
proceeding with a stale one. This slice dodges the problem (the hub token is used once, at
bootstrap), but Phases 3–4 cannot. The fix is a change to §2, which triggers the cross-repo docs
rule in [CLAUDE.md](../CLAUDE.md).

**6.3 · No invalidation.** Agents may cache any `GET`, with "cache lifetime the agent's choice",
and there is no webhook, ETag or revision counter — only an `updated_at` field. Change a project's
base URL at the hub and Q-Agent keeps testing the old environment until its cache happens to
expire. That is a smaller version of the exact drift ADR 0001 exists to remove. Options: a revision
counter with `If-None-Match`, or a rule that agents re-read config at the start of every run rather
than caching across runs.

---

## 7. Open decisions

1. **Email-collision policy** — a hub user whose email already exists as a local Q-Agent user:
   auto-link (recommended, and audited) or refuse and require admin action? Security-relevant
   default, not a detail.
2. **Role authority** — the token carries `role`. [INTEGRATION §1](INTEGRATION.md#1-principles)
   ("the hub authenticates; agents authorise") argues Q-Agent takes only *identity* from the token
   and keeps its own permissions.
3. **Are the tunnel hostnames live?** The mechanism depends on both apps being on
   `*.chuongnd.click` over HTTPS, and cannot be validated end-to-end on localhost (§8).
4. **`EMEHUB_AGENT_DAGENT_URL` default** — see §5.
5. **Q-Agent's own fail-open.** `q-agent/api/app/config.py:58` `QAGENT_AUTH_REQUIRED` makes the
   guard a passthrough, and Q-Agent's entire test suite runs with it off. This is the same class of
   bug as DAgent's `authDisabled()` that §6.1 of INTEGRATION says to *remove, not supplement*, and
   it sits directly in this work's path. Removing it means fixing every test's auth posture — in
   scope now, or a tracked exception?

---

## 8. Verification

**Gates.** `uv run pytest -q` per API; `npm run typecheck && npm run build` per frontend — neither
has a unit-test harness, so **there is no `npm test`**; `docker compose up -d --build` after
shipping. **Baseline Q-Agent's suite first**: 22 of 520 tests already fail on its `master`
(q-agent#469), so compare against that baseline rather than expecting green.

**Stage 1 — A1, unit level, no browser.** Mint succeeds for `qagent`; refused for `emehub` and for
an unregistered audience; 401 without the cookie; 403 on CSRF mismatch; refused for a revoked
session and for an inactive user; **the refresh token hash is byte-identical before and after** —
the test that pins the whole design. Also confirm the route reaches its handler at all: that is the
`PUBLIC_PATHS` exact-match trap, and getting it wrong produces a 401 at the middleware before the
handler is ever entered.

**Stage 2 — A2–A4.** `curl -H "Authorization: Bearer <emehub token>" localhost:8790/agents` returns
both agents with the right `handoffReady` / `reason`. Playwright at `localhost:5180/app`: Q-Agent's
Launch enabled, D-Agent's disabled with its tooltip, zero console errors, light and dark. Then
unset `EMEHUB_AGENT_QAGENT_URL`, restart, and confirm the card degrades and the audience drops.

**Stage 3 — B1–B3, requires the tunnel.** Over HTTPS on `*.chuongnd.click`: log in at
`hub.chuongnd.click` and confirm in devtools that `emehub_refresh` carries `Domain=.chuongnd.click`,
`Secure` and `HttpOnly`. Overview → Launch QAgent → land at `qagent.chuongnd.click`
**authenticated, with no second login** — verbatim the ROADMAP Phase 2 exit criterion. Assert:
`qagent_refresh` is set; `users.hub_user_id` is populated; an existing user's runs, evidence and
workspace path are untouched; a run WebSocket connects with a hub-derived session.

**Stage 4 — the race this design exists to prevent.** With the hub tab still open, launch Q-Agent,
then force a refresh in the hub tab. **The hub session must survive.** This needs an explicit
manual check, not just a unit test.

**Stage 5 — negatives and non-regression.** Stop the hub container and reload Q-Agent → "EmeHub is
unreachable", not the login form. Q-Agent's own login works with `QAGENT_HUB_SSO_ENABLED` both off
and on. `npm run dev` on both apps is unaffected with the flag off.

**Localhost caveat.** All `localhost` ports share one cookie jar, so the flow appears to work in dev
for the wrong reason and never exercises `Secure` or real `SameSite` behaviour. Treat localhost as
adequate for Stages 1–2 only; Stages 3–5 must run against the tunnel.

---

## 9. Out of scope

- **DAgent onboarding** (Phase 5) — §5.
- Proxying and then deleting Q-Agent's `/auth/*`, and the wholesale user migration. Argon2 hashes
  and plaintext TOTP secrets are portable; sessions are not, so that step logs everyone out once at
  a scheduled time.
- The `QAGENT_SECRET_KEY` re-key (Phase 3) — a decrypt-with-old / re-encrypt-with-new operation that
  **must not** be bundled with the user migration.
- Q-Agent reading hub configuration (Phases 3–4).
- Context and deep-link hand-off ("open this ticket in QAgent") — [ROADMAP](ROADMAP.md) lists
  cross-agent hand-off as not scheduled.
- RS256 + JWKS. `kid` is already emitted, so this stays additive.
- The single-use hand-off code flow — documented in ADR 0008 as the fallback, not built.
