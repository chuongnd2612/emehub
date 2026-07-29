# EmeHub

> One workspace for every EMESOFT agent.

EmeHub is the **source of truth** for everything the EMESOFT agent suite shares: who you are,
which Claude account you use, which Azure DevOps / GitHub / Jira org you're connected to,
which projects and repositories exist, and what we know about them. The specialised agents —
QAgent for QA, DAgent for development — stop owning those concerns and consume them from the
hub over HTTP, authenticated with a hub-issued token.

It is also the front door: sign in once, see the suite, launch an agent.

```
                    ┌─────────────────────────────┐
                    │          EmeHub             │
                    │  identity · users · roles   │
                    │  Claude credentials         │
                    │  provider connections       │
                    │  projects · knowledge       │
                    │  tickets · audit            │
                    └──────┬───────────────┬──────┘
                  JWT +    │               │    JWT +
                  config   │               │    config
                    ┌──────┴──────┐ ┌──────┴──────┐
                    │   QAgent    │ │   DAgent    │
                    │  runs·specs │ │ executions  │
                    │  evidence   │ │ worktrees   │
                    │  execution  │ │ skills      │
                    └─────────────┘ └─────────────┘
```

---

## Status

**The hub is built and running.** FastAPI + PostgreSQL behind nginx, ~408 backend tests, and
all eleven views from the design handoff live against real endpoints — Landing, Overview,
Projects & Repositories (list + five detail tabs), Tickets, Import dialog, Claude Settings,
Authentication, User Management, Integrations, Settings and the overlays, in light and dark
across four accents.

It owns identity (login, MFA, sessions, invites, roles), Claude credentials, provider
connections with live Azure DevOps / GitHub / Jira adapters, projects and their configuration,
knowledge bases — **which it now builds itself**
([ADR 0007](docs/adr/0007-knowledge-builds-run-on-the-hub.md)) — and the ticket store.

**What has not happened is the agent cutover.** Neither Q-Agent nor D-Agent validates a
hub token or reads its configuration from here, so the hub currently runs *alongside* both
rather than in front of them. That is the remaining work; see
[docs/ROADMAP.md](docs/ROADMAP.md).

Known gaps: [#50](https://github.com/chuongnd2612/emehub/issues/50) — a handful of designed
screens (API keys, roles, invitations, Overview activity/KPIs) have no backend behind them
and say so in the UI rather than showing fixtures as if they were real.

---

## The suite

| Agent | Discipline | Status | Repository |
|---|---|---|---|
| **QAgent** | QA / QC — tickets → test cases → Playwright runs → evidence → publish | Live | [`chuongnd2612/q-agent`](https://github.com/chuongnd2612/q-agent) |
| **DAgent** | Development — tickets → branch → code → commit → PR | In development | [`DaoLinh98/ticket-executor`](https://github.com/DaoLinh98/ticket-executor) (to be renamed `d-agent`) |
| **BAgent** | Business analysis — requirements, user stories, acceptance criteria | Planned | — |

Further agents sketched in the design mockup: DataAgent, OpsAgent, DocAgent, SecAgent.

---

## What the hub owns

| Concern | What that means |
|---|---|
| **Identity & users** | One login for the whole suite. Users, roles (`admin` / `member`), invites, sessions, 2FA, password reset. The hub issues the access tokens the agents accept. |
| **Claude credentials** | One place to add and rotate the Anthropic/Claude credential. Per-user credentials with an optional shared organisation account; agents resolve theirs from the hub instead of storing their own. |
| **Provider connections** | Azure DevOps / GitHub / Jira org URLs and PATs, stored encrypted once and reused by every agent. |
| **Projects & knowledge** | The project registry, its repositories, environments and test accounts — plus the per-repository knowledge base that agents read before they generate anything. The hub **builds** those knowledge bases too ([ADR 0007](docs/adr/0007-knowledge-builds-run-on-the-hub.md)), so an agent with no build capability of its own still gets one. |
| **Tickets** | The synced ticket store, so a ticket looked at in QAgent is the same ticket DAgent implements. |
| **Audit** | One audit trail across the suite. |

## What each agent keeps

The hub is deliberately **not** a place for domain work. The one narrow exception is that it
builds the shared artefacts it already owns every input for — knowledge bases
([ADR 0007](docs/adr/0007-knowledge-builds-run-on-the-hub.md)). It does not do an agent's job:
no test generation, no code generation, no browser automation, no PR creation. Each agent keeps
everything specific to its discipline:

- **QAgent** — runs, the eight-stage pipeline, generated specs, execution, evidence,
  self-healing, publishing back to the provider, the paired Local Agent.
- **DAgent** — executions, the Claude CLI stream runner, git worktrees, skill packs, plan
  gating and PR creation.

---

## Repository topology

The three repositories are siblings on disk:

```
claude-projects/
  emehub/            this repo — the hub
  q-agent/           QAgent  (chuongnd2612/q-agent)
  ticket-executor/   DAgent  (DaoLinh98/ticket-executor)
```

> **Open item:** the three repositories are owned by two different GitHub accounts today.
> The cross-repo delivery rule in [CLAUDE.md](CLAUDE.md) assumes shared access to all three;
> consolidating them under one organisation is unresolved. See
> [docs/INTEGRATION.md](docs/INTEGRATION.md#open-items).

---

## Architecture

| | Choice | Why |
|---|---|---|
| Backend | FastAPI (Python 3.13), SQLAlchemy 2 + Alembic | Mirrors QAgent, so its auth, crypto and ownership code ports near-verbatim. [ADR 0002](docs/adr/0002-stack-fastapi-react-mirroring-q-agent.md) |
| Frontend | React 19 + Vite + TypeScript + Tailwind 4 | Same as QAgent; the auth screens and design system carry over. |
| Database | PostgreSQL 16 | Same as both agents. |
| Deployment | Docker Compose — `api` + `db` + `web` (nginx) | Same shape as QAgent's compose file. |
| Integration | REST + hub-issued JWT; no shared database | Clean service boundary. [ADR 0003](docs/adr/0003-integration-via-http-and-hub-issued-jwt.md) |
| Design | Glassmorphic, light + dark, four accents (default EMESOFT Red) | The design handoff is binding. [ADR 0006](docs/adr/0006-implementing-the-emehub-design-handoff.md) |

All three are built and running. The `api` image also carries `git`, Node 20 and the Claude
CLI, because the hub builds knowledge bases itself
([ADR 0007](docs/adr/0007-knowledge-builds-run-on-the-hub.md)) — deliberately no chromium,
which would only be needed for browser automation the hub does not do.

---

## Documentation

| Document | What's in it |
|---|---|
| [docs/CONTEXT.md](docs/CONTEXT.md) | Domain glossary, and who owns what across the three apps. |
| [docs/ROADMAP.md](docs/ROADMAP.md) | The phased migration, Phase 0 → Phase 5. |
| [docs/INTEGRATION.md](docs/INTEGRATION.md) | The contract: token claims, config endpoints, degradation, known blockers. |
| [CLAUDE.md](CLAUDE.md) | Conventions and gates for anyone (human or agent) working in this repo. |
| [design/DESIGN_SYSTEM.md](design/DESIGN_SYSTEM.md) | Colour, type, components, motion. |
| [design/design_handoff_emehub/](design/design_handoff_emehub/) | **The binding design spec** — README, prototype, tokens, motion. |

### Architecture decisions

| ADR | Decision |
|---|---|
| [0001](docs/adr/0001-emehub-is-the-source-of-truth.md) | EmeHub is the source of truth, not a launcher. |
| [0002](docs/adr/0002-stack-fastapi-react-mirroring-q-agent.md) | FastAPI + React/Vite, mirroring QAgent's layout. |
| [0003](docs/adr/0003-integration-via-http-and-hub-issued-jwt.md) | Agents integrate over HTTP with a hub-issued JWT. |
| [0004](docs/adr/0004-inherit-the-q-agent-design-system.md) | Inherit the QAgent design system. |
| [0005](docs/adr/0005-secret-and-key-management.md) | Separate the signing secret from the encryption key. |
| [0006](docs/adr/0006-implementing-the-emehub-design-handoff.md) | The design handoff is binding; supersedes 0004. |
| [0007](docs/adr/0007-knowledge-builds-run-on-the-hub.md) | Knowledge builds run on the hub; narrows 0001 and supersedes the Phase 4 filesystem split. |

---

## Getting started

```bash
cp .env.example .env
# Generate the two secrets — they must be different values (ADR 0005).
# The API refuses to start if either is missing; there is no generated fallback.
python -c "import secrets; print(secrets.token_urlsafe(48))"   # -> EMEHUB_JWT_SECRET
python -c "import secrets; print(secrets.token_urlsafe(48))"   # -> EMEHUB_ENCRYPTION_KEY

docker compose up -d --build
```

- Hub UI — <http://localhost:5180>
- Health — <http://localhost:5180/api/health>

Ports (5180 web, 8790 api, 5457 db) are chosen not to clash with QAgent's, so both stacks can
run on one host during the migration.

**The first `--build` takes a few minutes.** Since
[ADR 0007](docs/adr/0007-knowledge-builds-run-on-the-hub.md) the hub builds knowledge bases
itself, so the API image also installs `git`, the Node 20 runtime and
`@anthropic-ai/claude-code` on top of the Python base. (No chromium — the hub runs no browser.)
Confirm the three are present after a build:

```bash
docker compose exec api sh -c 'git --version && node --version && claude --version'
```

Two things a build needs at runtime, neither of which the stack can supply for you:

- **a Claude credential** — upload one under *Claude settings*, or have an admin configure the
  shared account;
- **a repository connection with a PAT** — under *Integrations*, bound to the project whose
  repository you want cloned.

Without either, a build lands the knowledge row in `error` with a message saying which one is
missing; it never fails the request.

The `emehub-workspace` volume now holds repository clones and, for the duration of a build, a
decrypted Claude credential. Treat it as sensitive: not a world-readable mount, not a volume
to copy casually.

### Working on the frontend

```bash
cd app
npm install
npm run dev          # Vite on 5180, proxying /api to 127.0.0.1:8790
npm run typecheck    # tsc -b --noEmit
npm run build
```

`typecheck` + `build` are the gate. There is **no** unit-test harness — don't run `npm test`.
Verify UI behaviour at runtime with Playwright. See [CLAUDE.md](CLAUDE.md).

---

© EMESOFT · EmeHub — one workspace for every agent.
