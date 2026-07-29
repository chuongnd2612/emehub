# ADR 0001 — EmeHub is the source of truth, not a launcher

- **Status:** Accepted, **amended by [ADR 0007](0007-knowledge-builds-run-on-the-hub.md)** (2026-07-29)
- **Date:** 2026-07-28

> **Amendment.** The "agents own the domain work" boundary below now has one carve-out:
> the hub *builds the shared artefacts it already owns the inputs for* — specifically
> knowledge bases, whose repository connection, PAT, project config and Claude credential all
> already live here. The rule is now "the hub builds hub-owned data; it does not do an agent's
> job." No test generation, no code generation, no browser automation, no PR creation. See
> [ADR 0007](0007-knowledge-builds-run-on-the-hub.md).

## Context

EMESOFT has two agent applications and intends to build more. They were developed
independently and each grew its own version of the same platform concerns:

| Concern | QAgent | DAgent (`ticket-executor`) |
|---|---|---|
| Identity | Users, roles, invites, sessions, TOTP, JWT + refresh cookie (`api/app/services/auth_service.py`) | One shared password hashed into an HMAC cookie, no user records (`lib/auth.ts`) |
| Claude credential | Per-user encrypted `.credentials.json`, shared-account fallback (`api/app/models/claude_credentials.py`) | None — relies on whichever `claude` CLI is logged in on the host |
| Provider credential | `provider_connections`, Fernet-encrypted PAT, ADO + GitHub + Jira adapters | `ProviderCredential`, AES-256-GCM PAT, ADO complete and GitHub partial |
| Projects / knowledge | `project_config` + `project_knowledge` keyed `project::repo` | None; "root repo" is a free-text field per ticket |
| Tickets | Synced into a `tickets` table | Fetched live, never persisted |

There is no shared code and no shared data between them. A user configures their Azure DevOps
PAT twice, and the two apps disagree about who that user even is.

A third agent would make it three of everything.

## Options considered

1. **Launcher / portal.** A front page that links to each agent. Each app keeps its own auth
   and configuration. Cheap; solves nothing — the duplication and drift remain.
2. **Shared library.** Extract the platform concerns into packages the apps import. Removes
   code duplication but not *data* duplication: two databases still hold two user tables, and
   a Python package cannot be imported by a Next.js app anyway.
3. **Source of truth service.** A hub that owns identity and shared configuration; agents
   consume it over HTTP.

## Decision

**Option 3.** EmeHub is a real service that owns:

- identity — users, roles, sessions, 2FA, invites, password reset;
- Claude credentials;
- provider connections;
- projects, repositories and knowledge bases;
- tickets;
- the audit trail.

Agents own only their discipline: QAgent keeps runs, specs, evidence, execution and the paired
Local Agent; DAgent keeps executions, worktrees, skills and PR creation.

QAgent's platform code migrates into the hub and is then deleted from QAgent. DAgent's shared
password is deleted outright.

## Consequences

**Good.** One login for the suite. One place to rotate a Claude credential or a PAT. A ticket
means the same thing in both agents. A knowledge base built once serves both. New agents get
the platform for free — the marginal cost of BAgent drops sharply.

**Bad.** The hub becomes a hard dependency, and a single point of failure for authentication.
[INTEGRATION.md §5](../INTEGRATION.md#5-degradation) specifies degradation deliberately
rather than leaving it to chance.

**Expensive.** This is a migration of a live application, not a greenfield build. QAgent has
real users and real encrypted rows. Phases 2 and 3 in [ROADMAP.md](../ROADMAP.md) each carry a
data migration, and the credential migration is a re-key, not a copy
([ADR 0005](0005-secret-and-key-management.md)).

**Deferred.** Whether the hub introduces a real organisation/team entity, or inherits QAgent's
nullable `owner_id` + `shared` convention, is not decided here. It must be decided before
Phase 2 writes the user schema.
