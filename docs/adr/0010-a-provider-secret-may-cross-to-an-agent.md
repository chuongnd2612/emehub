# 10. A provider secret may cross to an agent

Date: 2026-08-06

## Status

Accepted. **Supersedes the "not recommended" verdict on returning a PAT** in
[INTEGRATION.md §4](../INTEGRATION.md#4-secrets-that-cross-the-boundary).

## Context

Every provider operation an agent performs is now covered by a narrow endpoint where the *hub*
makes the call: `POST /tickets/sync`, the comment and test-case read-throughs, and the three
`POST /tickets/{external_id}/…` writes. The secret never has to move because it never needs to —
the call happens on the side that holds it. That pattern settled the general case, and §4 records
it as the preferred answer rather than a stopgap.

§4 also records the two cases it does **not** cover:

> **cloning a repository** (the PAT has to be injected into a git remote on the machine doing the
> clone) and **anything DAgent hands to an MCP server**, which needs the credential locally by
> construction. Those need the scoped-short-lived-token answer, per provider, or nothing.

Both are DAgent, and both are structural rather than unimplemented. DAgent does not call the
provider. It writes an MCP config file and starts a Claude CLI subprocess, which starts
`@azure-devops/mcp` as a *further* child process, and that process makes the calls:

```ts
// ticket-executor/lib/mcp.ts:69-72
build: (org, pat) => {
  const slug = parseAdoUrl(org).org;
  if (!slug || !pat) return null;
  const env = { AZURE_DEVOPS_TOKEN: pat };
```

There is no seam to insert a hub call into. The credential has to be in that process's
environment, or the run does not happen.

So the escape hatch §4 offers is the scoped short-lived token — and for the providers DAgent
actually uses it does not exist. GitHub has installation tokens; classic Azure DevOps and Jira PATs
have no equivalent. For DAgent the sentence resolves to **"or nothing"**, and "nothing" means
ROADMAP Phase 5 cannot complete: DAgent could take identity and a Claude credential from the hub
and still be unable to execute a single ticket.

Refusing here would not keep the PAT in one place either. It would keep DAgent's own
`ProviderCredential` table alive permanently, which is the duplication this whole project exists to
remove — the same Azure DevOps PAT configured twice, in the hub's founding ADR's own motivating
example.

## Decision

Add **`GET /connections/{id}/secret`**, returning the decrypted PAT to an agent audience.

```jsonc
// 200
{ "id": 1, "kind": "azure_devops", "label": "New Azure DevOps connection",
  "baseUrl": "https://dev.azure.com/…/", "config": {"project": ""},
  "capabilities": ["work_item", "repository"],
  "pat": "…", "updatedAt": "2026-08-06T04:29:05Z" }
```

### What keeps it narrow

1. **Agent audiences only.** `require_principal`, then `emehub` refused explicitly — the same guard
   `POST /auth/agent-grant` applies, for the same reason. The hub's own SPA deliberately never
   displays a PAT, so a browser origin must not be able to read one. This makes it the only route
   in the hub an agent token reaches that a hub token does not.
2. **Its own response model.** `ConnectionOut` gains nothing; `_out()` is untouched and still cannot
   leak. Two schemas rather than one optional field, so "does this response carry a secret" stays a
   question answered by reading the type.
3. **Scoped through `app.services.ownership`.** Another member's connection 404s, exactly as it does
   for every other connection read.
4. **Audited on every call** — success, miss and failure alike, as `GET /credentials/claude/resolve`
   already is. This is the second endpoint in the hub that returns a secret, and the audit row is
   the only record that it happened.
5. **An undecryptable blob is a `502`, never an empty string.** The same rule the provider
   read-throughs apply, one level down.

### Change detection costs nothing new

An agent that stores the PAT has to notice a rotation. `provider_connections.updated_at` already
carries `onupdate=utcnow`, so any write — a rotated PAT included — bumps it, and `GET /connections`
already returns it. The agent compares what it holds against the list and re-reads `/secret` only
for rows that moved.

Deliberately not a webhook: a push would need the hub to reach an agent that may be on a
developer's laptop, plus retries and ordering, to deliver something a single list call already
answers. It is also the first concrete answer to the "no cache invalidation" gap §3 records.

## Alternatives considered

**Revive `POST /connections/{id}/proxy`.** Still an SSRF and header-leak surface, and it would not
help: the caller here is an MCP subprocess the hub has no relationship with, not the agent's own
code. A forwarder cannot proxy for a process that will not ask it.

**Per-provider scoped short-lived tokens.** The right answer where the provider offers one, and
GitHub does. Azure DevOps and Jira classic PATs do not, and those are what DAgent runs on. Worth
revisiting per provider; it does not unblock anything today.

**Keep DAgent's own `provider_connections` table forever.** The honest status quo, and the reason
to reject it is not tidiness: the user configures the same PAT twice, the two copies rotate
independently, and the hub's `/connections` stays a display of configuration it does not govern.

**Hand the PAT out through a run-scoped grant** (extending [ADR 0009](0009-run-scoped-credential-grants.md)
with a `provider-credential` scope). Attractive, and not needed yet: the agent resolves at sync
time from a browser-driven call, not from a background thread past the 15-minute window. If an agent
ever prefers resolve-per-run over storing, this is the shape to add — the grant machinery already
exists and already dies with the hub session.

## Consequences

- **The hub now returns two kinds of secret.** `/credentials/claude/resolve` and this. Both are
  audited, both are agent-only, and both are single-purpose endpoints with a dedicated response
  model. That should remain the complete list, and a third one deserves its own ADR rather than an
  extension of this.
- **The PAT exists in two places once an agent stores it.** That is the cost, and it is paid down by
  the hub staying the place it is *edited*: the agent's copy is a mirror keyed on `updatedAt`, never
  an independently-editable second source. An agent that lets a user edit a mirrored connection
  re-creates exactly the drift this removes.
- **`test_the_pat_never_appears_in_any_connection_response` needed updating by hand**, and that
  friction is intentional — the same reasoning ADR 0009 recorded for the guard-dependency tests. A
  new route must not be able to satisfy a "nothing leaks" assertion by being forgotten.
- INTEGRATION.md §4's PAT paragraph and its "genuinely uncovered" sentence are rewritten, not
  annotated. A decision that contradicts a written one replaces it.
- ROADMAP Phase 5 loses one of DAgent's four blockers. The remaining three — no user model, a
  fail-open auth gate, no containerisation — are all agent-side.
