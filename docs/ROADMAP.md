# EmeHub — Roadmap

From an empty repository to the hub owning identity and shared configuration for both agents.

Phases are sequential: each one leaves all three applications working. There is no phase in
which the suite is half-migrated and broken.

---

## Phase 0 — Scaffold *(current)*

The repository, the documentation and the architecture decisions.

- README, CLAUDE.md, [CONTEXT.md](CONTEXT.md), [INTEGRATION.md](INTEGRATION.md), ADRs 0001–0005.
- Design system and landing mockup inherited from QAgent.
- Nothing runs.

**Exit criteria:** the contract in [INTEGRATION.md](INTEGRATION.md) has been read and
disagreed with, or accepted.

---

## Phase 1 — Skeleton

A hub you can start.

- `api/` — FastAPI app, Postgres, Alembic, config via `EMEHUB_*` env, `/health`.
- `app/` — React 19 + Vite + Tailwind 4 shell, the design system as tokens.
- `docker-compose.yml` — `api` + `db` + `web` (nginx), mirroring QAgent's topology on
  non-clashing ports.
- The **landing page** built from [`design/EmeHub.dc.html`](../design/EmeHub.dc.html): hero,
  suite grid, how-it-works, footer. Agent cards link out to the running agents.

**Exit criteria:** `docker compose up -d --build` serves the landing page; `/health` is green;
`npm run typecheck && npm run build` pass.

**Open question to answer first:** the visual design is being reworked — the landing page
should not be built twice. Either wait for the new design or build the shell and defer the
landing page to the end of this phase.

---

## Phase 2 — Identity

The hub becomes the login for the suite.

- Port from QAgent: `services/auth_service.py`, `deps_auth.py`, `models/user.py`,
  `models/session.py`, the `auth_guard` middleware, and the `/auth/*` router.
- Port the UI: login, forgot/reset password, profile, 2FA, sessions, user management.
- Add **audience-scoped token issue** (`aud`), which QAgent does not have today.
- QAgent switches to validating hub tokens. Its own `/auth/*` becomes a thin proxy to the hub
  first (so nothing breaks in one step), then is deleted.

**Data migration.** QAgent has live users. Argon2 password hashes are portable — they move as
opaque strings and users keep their passwords. TOTP secrets are stored in plaintext in
`users.totp_secret` and move as-is. Sessions do **not** migrate: everyone is logged out once,
at a scheduled time.

**Decide before writing the schema:** whether to introduce a real organisation/team entity or
inherit QAgent's `owner_id` + `shared` convention. Retrofitting later is a migration across
every table. See [INTEGRATION.md](INTEGRATION.md#open-items).

**Exit criteria:** a user logs in at the hub and lands in QAgent authenticated, without a
second login. QAgent's `users` and `auth_sessions` tables are gone.

---

## Phase 3 — Credentials

- **Claude credentials** move: model, encryption, resolution precedence (own → shared →
  none), the `prefer_shared` flag, usage/stat capture, and `GET /credentials/claude/resolve`.
- **Provider connections** move: the connection model, capability binding, and connection
  testing. Adapters (Azure DevOps, GitHub, Jira) move with them, or the hub proxies provider
  calls — decided per provider, see [INTEGRATION.md §4](INTEGRATION.md#4-secrets-that-cross-the-boundary).
- Upgrade token signing to RS256 + JWKS, retiring the shared secret.

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

- Project registry, configuration, environments, test accounts, repositories.
- Knowledge bases, including the write path so QAgent can contribute runtime-verified
  selectors back.
- Ticket sync.

**The hard part is not the data, it is the filesystem.** QAgent's knowledge lives both in
Postgres and in per-user workspace directories (`workspace/users/<id>/knowledge/…`), and repo
clones live on the QAgent host. The hub owning the *metadata* while the *clone* stays on the
agent host is likely the right split, but it needs deciding before this phase starts.

**Exit criteria:** a project created at the hub is visible in QAgent, and a knowledge base
built once serves both agents.

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
