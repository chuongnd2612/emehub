# ADR 0002 — FastAPI + React/Vite, mirroring QAgent's layout

- **Status:** Accepted
- **Date:** 2026-07-28

## Context

The hub needs a stack. Two precedents exist in-house, and they disagree:

- **QAgent** — FastAPI (Python 3.13), SQLAlchemy 2 + Alembic, React 19 + Vite 6 + Tailwind 4,
  Postgres 16, Docker Compose with nginx. Multi-user, deployed, in production use.
- **DAgent** — Next.js 16 App Router, Prisma, Postgres. Single process, local developer tool,
  no deployment story at all.

Almost everything the hub must own in Phases 2–4 already exists, working and tested, in
QAgent's Python:

| What | Where |
|---|---|
| Argon2 hashing, HS256 JWTs, TOTP, CSRF, refresh-token rotation | `api/app/services/auth_service.py` |
| `require_user` / `require_admin` / `require_role` dependencies | `api/app/deps_auth.py` |
| Global auth middleware, admin seeding | `api/app/main.py` |
| Fernet encryption with an `enc::` prefix | `api/app/crypto.py` |
| Ownership scoping helpers | `api/app/services/ownership.py`, `workspace_scope.py` |
| Claude credential store, resolution, materialisation | `api/app/services/claude_credentials.py` |
| Provider connections + ADO/GitHub/Jira adapters | `api/app/services/adapters/` |
| Auth screens, settings screens, user management | `app/src/screens/auth/**`, `screens/settings/**` |

## Options considered

1. **Next.js, mirroring DAgent.** One codebase for server and UI, faster to stand up, and it
   matches the app most likely to need the most work later. But every reusable asset above is
   Python and would be rewritten — including the security-sensitive parts, which is exactly
   the code you least want to reimplement from memory.
2. **UI-only hub on QAgent's existing API.** No new backend. But it makes the hub a feature of
   QAgent rather than a peer of it, which contradicts
   [ADR 0001](0001-emehub-is-the-source-of-truth.md): QAgent cannot both be a consumer of the
   hub and be the hub.
3. **FastAPI + React/Vite, mirroring QAgent.**

## Decision

**Option 3.** The hub uses QAgent's stack and repository layout:

```
emehub/
  api/                FastAPI, SQLAlchemy 2, Alembic, Postgres
  app/                React 19, Vite, TypeScript, Tailwind 4
  docker-compose.yml  api + db + web (nginx)
```

Configuration is prefixed `EMEHUB_` and ports are chosen not to clash with QAgent's, so both
stacks can run on one host during migration.

## Consequences

**Good.** The auth, crypto, ownership and credential code moves largely verbatim, and moving
working security code is safer than rewriting it. The frontend inherits QAgent's auth screens,
settings components and design system. Anyone who can work in QAgent can work in the hub.

**Bad.** Two languages in the suite: the hub and QAgent are Python, DAgent is TypeScript.
There is no shared client library — DAgent hand-writes its hub client. Accepted: the
integration surface is small and specified in
[INTEGRATION.md](../INTEGRATION.md), and an OpenAPI schema can generate a TypeScript client
later if it becomes tedious.

**Bad.** "Mirroring QAgent" copies QAgent's weaknesses too, if done carelessly — notably a
global auth middleware with a path allowlist rather than per-route dependencies, and
hand-rolled token handling for static files and WebSockets. Port these deliberately, not by
copy-paste. The one weakness explicitly *not* inherited is the conflated secret
([ADR 0005](0005-secret-and-key-management.md)).

**Note.** Neither QAgent's frontend nor the hub's will have a unit-test harness; the gate is
`npm run typecheck` + `npm run build`, with runtime verification via Playwright. This is a
carried-over constraint, not an endorsement.
