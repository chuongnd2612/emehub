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

**Phase 0 — scaffold.** This repository currently contains documentation and architecture
decisions only. There is no application code yet.

Both agents still own their own authentication and credentials today; nothing has been
migrated. See [docs/ROADMAP.md](docs/ROADMAP.md) for the phased plan and
[docs/INTEGRATION.md](docs/INTEGRATION.md) for the contract the agents will implement.

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
| **Projects & knowledge** | The project registry, its repositories, environments and test accounts — plus the per-repository knowledge base that agents read before they generate anything. |
| **Tickets** | The synced ticket store, so a ticket looked at in QAgent is the same ticket DAgent implements. |
| **Audit** | One audit trail across the suite. |

## What each agent keeps

The hub is deliberately **not** a place for domain work. Each agent keeps everything specific
to its discipline:

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
| Design | Dark, glassmorphic, purple→indigo | Inherited wholesale. [ADR 0004](docs/adr/0004-inherit-the-q-agent-design-system.md) |

Nothing in the table above is built yet — it is the target that Phase 1 implements.

---

## Documentation

| Document | What's in it |
|---|---|
| [docs/CONTEXT.md](docs/CONTEXT.md) | Domain glossary, and who owns what across the three apps. |
| [docs/ROADMAP.md](docs/ROADMAP.md) | The phased migration, Phase 0 → Phase 5. |
| [docs/INTEGRATION.md](docs/INTEGRATION.md) | The contract: token claims, config endpoints, degradation, known blockers. |
| [CLAUDE.md](CLAUDE.md) | Conventions and gates for anyone (human or agent) working in this repo. |
| [design/DESIGN_SYSTEM.md](design/DESIGN_SYSTEM.md) | Colour, type, components, motion. |
| [design/EmeHub.dc.html](design/EmeHub.dc.html) | The landing-page mockup this repo builds toward. |

### Architecture decisions

| ADR | Decision |
|---|---|
| [0001](docs/adr/0001-emehub-is-the-source-of-truth.md) | EmeHub is the source of truth, not a launcher. |
| [0002](docs/adr/0002-stack-fastapi-react-mirroring-q-agent.md) | FastAPI + React/Vite, mirroring QAgent's layout. |
| [0003](docs/adr/0003-integration-via-http-and-hub-issued-jwt.md) | Agents integrate over HTTP with a hub-issued JWT. |
| [0004](docs/adr/0004-inherit-the-q-agent-design-system.md) | Inherit the QAgent design system. |
| [0005](docs/adr/0005-secret-and-key-management.md) | Separate the signing secret from the encryption key. |

---

## Getting started

*Planned — there is nothing to run yet.* Once Phase 1 lands, this section will read roughly:

```bash
cp .env.example .env      # fill in EMEHUB_JWT_SECRET and EMEHUB_ENCRYPTION_KEY
docker compose up -d --build
# hub UI  → http://localhost:5180
# hub API → http://localhost:8790/health
```

Until then, this repository is documentation. Start with
[docs/ROADMAP.md](docs/ROADMAP.md).

---

© EMESOFT · EmeHub — one workspace for every agent.
