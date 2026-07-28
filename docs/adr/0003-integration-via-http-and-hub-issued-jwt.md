# ADR 0003 — Agents integrate over HTTP with a hub-issued JWT

- **Status:** Accepted
- **Date:** 2026-07-28

## Context

[ADR 0001](0001-emehub-is-the-source-of-truth.md) makes the hub the owner of identity and
shared configuration. The agents now need a way to reach it. The three repositories are
separate, live in different languages, and deploy independently.

## Options considered

1. **Shared database, separate schemas.** One Postgres; the hub owns an `emehub` schema and
   the agents read it directly. No network hop, transactional reads, trivial to implement.
   But it couples deployments and migrations across three repositories, lets any agent write
   to hub tables with nothing to stop it, and makes the hub's schema a public API that can
   never be refactored. It also cannot work across the language boundary without duplicating
   the schema definition in Prisma *and* SQLAlchemy.
2. **Monorepo / git submodules with extracted shared packages.** Genuine code sharing, one
   version of the truth. But it means restructuring three working repositories before any
   value is delivered, and still does not solve Python↔TypeScript sharing.
3. **HTTP APIs with a hub-issued JWT.**

## Decision

**Option 3.**

- The hub issues short-lived HS256 access tokens with an `aud` claim naming the consuming
  agent (`qagent`, `dagent`). Agents validate signature, `iss`, `aud` and `exp` **locally** —
  no callback to the hub per request.
- Refresh happens only at the hub, against an HttpOnly refresh cookie. Agents never mint,
  refresh or extend tokens.
- Configuration is read over REST. Agents may cache; agents never hold an authoritative copy.
- No agent connects to the hub's database.

The full contract — claims, endpoints, degradation behaviour — is
[INTEGRATION.md](../INTEGRATION.md), which is versioned alongside the code and changed by PR.

Key distribution starts as a shared secret (Phase 1) and upgrades to RS256 + a published JWKS
(Phase 3). The `kid` header is present from the first token so the upgrade is not breaking.

## Consequences

**Good.** A clean, inspectable boundary. Each application deploys on its own schedule. The
hub can refactor its schema freely as long as the documented endpoints hold. Local token
validation means a hub outage does not stop in-flight work.

**Bad.** More plumbing than a shared database: a client in each agent, caching, retries, and
an error path for every call. Two languages means two hand-written clients.

**Bad.** Eventual consistency. An agent's cached project list can be stale. Accepted — the
data is configuration, not transactions.

**Sharp edge.** Some secrets must still cross the boundary. The Claude credential is returned
to the agent because the Claude CLI needs it on disk. The provider PAT is *not* returned; the
hub proxies provider calls instead. Both are specified in
[INTEGRATION.md §4](../INTEGRATION.md#4-secrets-that-cross-the-boundary) rather than left to
whoever writes the endpoint.

**Non-negotiable.** No failing open on authentication. There is no configuration in which an
unreachable hub results in unauthenticated access being permitted.
