# EmeHub — Roadmap

From an empty repository to the hub owning identity and shared configuration for both agents.

Phases are sequential: each one leaves all three applications working. There is no phase in
which the suite is half-migrated and broken.

---

## Phase 0 — Scaffold *(done)*

The repository, the documentation and the architecture decisions.

- README, CLAUDE.md, [CONTEXT.md](CONTEXT.md), [INTEGRATION.md](INTEGRATION.md), ADRs 0001–0005.
- Design system and landing mockup inherited from QAgent.
- Nothing runs.

**Exit criteria:** the contract in [INTEGRATION.md](INTEGRATION.md) has been read and
disagreed with, or accepted.

---

## Phase 1 — The UI, against stubbed data *(done)*

The full design handoff, implemented. Scope expanded from "a landing page" once the complete
design landed in [`design/design_handoff_emehub/`](../design/design_handoff_emehub/)
([ADR 0006](adr/0006-implementing-the-emehub-design-handoff.md)).

- `app/` — React 19 + Vite + Tailwind 4. The token layer (light/dark × four accents),
  primitives, app shell, and all eleven views: Landing, Overview, Projects & Repositories,
  Tickets, Import dialog, Claude Settings, Authentication, User Management, Integrations,
  Settings, and the overlays.
- `app/src/data/` — a **typed stub layer** shaped like the handoff's *Data fetching* section.
  Every screen reads from it; no screen calls a real endpoint, because none exist.
- `api/` — minimal FastAPI + `/health` only. Real endpoints arrive in Phases 2–4.
- `docker-compose.yml` — `api` + `db` + `web` (nginx) on ports that don't clash with QAgent.

**Exit criteria — all met.** `docker compose up -d --build` serves the app (all three services
healthy); `typecheck` and `build` pass; 9 routes × 2 modes × 4 accents = 72 loads verified
against the *container* build with one canvas each and zero console errors; the light-mode
contrast audit went from 241 failing text elements to 2 (both the `#fff`-on-`#2684ff` Jira
logotype, which WCAG exempts).

**Two token corrections were needed**, because the handoff contradicts itself: its theme-token
table gives light `--muted` as `#6a7182`, while its own darkening map says
`#8b8b9e → #5c6273` — and `#8b8b9e` *is* the dark `--muted`. `#6a7182` measures 4.29:1,
breaking the handoff's stated ≥4.5:1 promise. `--terra` needed the same treatment for the code
chips inside the terracotta banner. Both are commented in `app/src/styles/theme.css`.

**Carried forward:** dark mode has its own contrast failures from the handoff's dark column
(`--label` 3.38:1, `--faint` 3.93:1) — [issue #26](https://github.com/chuongnd2612/emehub/issues/26),
a design decision rather than a defect fix.

**Note.** Phases 2–4 then replace stubs with real calls, one resource at a time. The stub
layer is the seam that makes that a per-file change rather than a rewrite.

---

## Phase 2 — Identity

> **Hub side: done. Agent cutover: shipped for QAgent** (identity only), **not started for
> DAgent.** Every phase below splits the same way, so the two halves are listed separately.

The hub becomes the login for the suite.

**Hub side — done.**
- ✅ Ported from QAgent: `services/auth_service.py`, `deps_auth.py`, `models/user.py`,
  `models/session.py`, the auth guard, and the `/auth/*` router.
- ✅ The UI: login, forgot/reset password, profile, 2FA, sessions, user management. Note the
  design handoff contains **no** login screen — those were derived from QAgent's and restyled,
  and still want a designer pass.
- ✅ **Audience-scoped tokens** (`aud`), which QAgent does not have. `kid` is present from the
  first token so the Phase-3 RS256/JWKS move is not breaking.
- ✅ **The sign-in hand-off** ([ADR 0008](adr/0008-cross-app-session-handoff.md)) —
  `POST /auth/agent-token` mints an agent-audience token from the shared refresh cookie **without
  rotating it**, `GET /agents` publishes the launch registry, and the Overview cards launch for
  real. Detail in [SSO-HANDOFF-PLAN.md](SSO-HANDOFF-PLAN.md).

  Two things this settled that the plan had left open. The hand-off deliberately does *not* reuse
  `/auth/refresh`, because that **rotates** — two SPAs sharing one rotating credential race and log
  each other out. And `registered` is now distinct from `handoffReady`: an agent can be registered
  (the hub mints it tokens) while single sign-on still cannot work, because
  `EMEHUB_COOKIE_DOMAIN` does not cover its origin. The UI surfaces the second, so it never offers
  a launch that fails after the click.

**Agent cutover — shipped for QAgent.** Slices B1–B5 of
`q-agent/docs/HUB-INTEGRATION.md` are merged ([q-agent#476](https://github.com/chuongnd2612/q-agent/issues/476)),
gated behind `QAGENT_HUB_SSO_ENABLED`:
- QAgent validates hub tokens alongside its own, branching on `iss`, and JIT-provisions a local user
  keyed on a new `users.hub_user_id`. **Local ids were kept and mapped rather than re-pointed** —
  every `owner_id`, run, evidence file and per-user workspace path keeps working, and no data
  migration ran.
- `POST /auth/sso/complete` returns a login-shaped body, so QAgent's auth store and its
  401→refresh→retry interceptor were untouched.
- Not done, and deliberately: QAgent's own `/auth/*` still exists rather than proxying here, and its
  `users` / `auth_sessions` tables are still live. The wholesale user migration — which logs
  everyone out once, at a scheduled time — has not been scheduled.
- Because the agent creates **its own** session from the handed-over token, the hub token is
  consumed once at bootstrap. **This phase therefore has no 15-minute-token problem** — that only
  arrives when QAgent starts *reading* hub configuration in Phases 3–4, where it is a genuine
  blocker.

**Data migration.** QAgent has live users. Argon2 password hashes are portable — they move as
opaque strings and users keep their passwords. TOTP secrets are stored in plaintext in
`users.totp_secret` and move as-is. Sessions do **not** migrate: everyone is logged out once,
at a scheduled time.

**Decided:** inherit QAgent's `owner_id` + `shared` convention — nullable `owner_id`, NULL
means the shared namespace. No organisation/team entity. Chosen so the eventual QAgent
migration is a row copy rather than a backfill; revisit only with a migration across every
scoped table.

**Exit criteria (cutover):** a user logs in at the hub and lands in QAgent authenticated,
without a second login. QAgent's `users` and `auth_sessions` tables are gone.

---

## Phase 3 — Credentials

> **Hub side: done.** Agent cutover: **not started**.

**Hub side — done.**
- ✅ **Claude credentials**: model, encryption, resolution precedence (own → shared → none),
  the `prefer_shared` flag, usage capture, and `GET /credentials/claude/resolve`. Only that
  one endpoint ever returns credential material, asserted structurally and behaviourally.
- ✅ **Provider connections**: the connection model, capability binding (`work_item` /
  `repository`), connection testing, and the Azure DevOps / GitHub / Jira adapters. The PAT is
  never returned — `GET /connections` says `hasPat` and nothing more.
- ✅ The UI for both.

**Not done.**
- `POST /connections/{id}/proxy` — deliberately unbuilt; a generic forwarder is an SSRF and
  header-leak surface that needs its own design
  ([INTEGRATION.md §4](INTEGRATION.md#4-secrets-that-cross-the-boundary)).
- RS256 + JWKS, retiring the shared secret. `kid` is already emitted so this is additive.
- Agent cutover.

**Data migration — this is the sharp edge.** Every encrypted value in QAgent
(`claude_credentials.credentials`, provider PATs, test-account passwords) is Fernet-encrypted
with a key derived from `QAGENT_SECRET_KEY`. The hub uses a *separate* `EMEHUB_ENCRYPTION_KEY`
([ADR 0005](adr/0005-secret-and-key-management.md)). Migration is therefore
**decrypt-with-old, re-encrypt-with-new** — a one-shot script that must run with both secrets
available, be idempotent, and be rehearsed against a database copy first.

**Exit criteria:** a Claude credential added once at the hub is used by a QAgent run. QAgent's
`claude_credentials` and `provider_connections` tables are gone.

---

## Phase 4 — Projects, knowledge and tickets

> **Hub side: done.** Agent cutover: **not started**.

**Hub side — done.**
- ✅ Project registry, configuration, environments, encrypted test accounts, repositories —
  including the full configuration UI (provider bindings, base URL, repository discovery from
  the bound connection, manual add) ported from QAgent's `ProjectSettingsForm` / `ReposManager`.
- ✅ Knowledge **metadata**, including the `PATCH` write path so an agent can contribute
  runtime-verified selectors back without clobbering existing `verified_at_runtime` entries.
- ✅ Ticket store, server-side filtering and paging, and sync through the adapters.
- ✅ **Knowledge builds, run on the hub** — see the reversal below.

**Reversed — the filesystem split.** This phase originally decided that the hub owns knowledge
*metadata* only: no clones, no `project-bootstrap`, no "Build knowledge" button, with the agent
building on its own host and reporting the result. That decision is **superseded by
[ADR 0007](adr/0007-knowledge-builds-run-on-the-hub.md)**. What it produced in practice was a
button that could not build anything, and it left D-Agent — which has no build capability and
no plans for one — permanently unable to obtain a knowledge base.

**What is true now.** The hub clones the repository into a per-owner workspace, runs
`project-bootstrap` through the Claude CLI against that clone, writes `knowledge.md` /
`knowledge.json` and updates the row itself.
`POST /projects/{key}/repos/{repo}/knowledge/build` starts the work in the background;
`indexing` is both the in-flight guard and the thing the UI polls. Builds are
concurrency-bounded (`EMEHUB_KNOWLEDGE_BUILD_CONCURRENCY`, default 2) and every failure mode
lands the row in `error` with an actionable `lastError`.

`PUT /projects/{key}/repos/{repo}/knowledge` **stays.** QAgent already builds its own knowledge
and can still report it, `docPath` and all. The hub is *a* builder, not the only one.

**Consequences to hold in view.** The API image now carries `git`, Node 20 and
`@anthropic-ai/claude-code` — no chromium, which ADR 0007 explicitly excludes. The
`emehub-workspace` volume holds a materialised Claude credential for the duration of a build
and must be treated as sensitive. And the hub is now a place where money is spent; usage is
attributed per owner in `claude_usage`.

The seam in `project_config_service.py` is unchanged: `storageState.json` is a browser artifact
and the hub still runs no browser.

**Exit criteria (cutover):** a project created at the hub is visible in QAgent, and a knowledge
base built once serves both agents.

---

## Phase 5 — DAgent onboards

- Delete `authDisabled()`, the `te_session` HMAC cookie and `/api/auth/*`
  ([INTEGRATION.md §6.1](INTEGRATION.md#61-dagents-auth-gate-disables-itself)).
- Replace the gate in `proxy.ts` with hub-token validation.
- Build credential materialisation so DAgent can run the Claude CLI with a hub-issued
  credential ([§6.2](INTEGRATION.md#62-dagent-has-no-server-side-claude-credential)).
- Read projects, repositories and tickets from the hub instead of discovering them per-run.

**Answer first:** does DAgent stay a local developer tool or become a hosted service? Its
`--dangerously-skip-permissions` execution model is fine for the former and unacceptable for
the latter. This question gates the whole phase.

**Exit criteria:** DAgent has no authentication of its own and no local-only credential path.

---

## Not scheduled

- BAgent and the rest of the suite (DataAgent, OpsAgent, DocAgent, SecAgent).
- Cross-agent hand-off as a product feature — carrying a ticket from DAgent to QAgent with
  one click. Cheap once Phase 4 lands, but a separate piece of work.
- SSO against an external IdP (Entra, Google Workspace). The hub is designed to be able to
  become an OIDC client later; nothing in Phases 1–5 should make that harder.
