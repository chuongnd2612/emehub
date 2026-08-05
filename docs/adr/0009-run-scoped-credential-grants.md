# 9. Run-scoped credential grants

Date: 2026-08-05

## Status

Accepted.

## Context

`GET /credentials/claude/resolve` has been complete since Phase 3. No agent can rely on it.

The hand-off in [ADR 0008](0008-cross-app-session-handoff.md) mints agent tokens from the
**browser's** shared refresh cookie. That is exactly right for signing in, and useless for the work
that follows: a QAgent run executes on a background daemon thread. There is no browser, no cookie,
and nothing to mint from.

The numbers do not work out:

| | |
|---|---|
| Agent access-token lifetime | **15 minutes** (`access_token_ttl_minutes`) |
| Agents refreshing their own tokens | Forbidden — [INTEGRATION.md §2](../INTEGRATION.md#2-token) |
| QAgent's Claude bootstrap timeout **alone** | 1200 s, and a full run is longer |

So a run that needs to resolve a credential after minute 15 has **no legal path**. And it cannot
shrug and continue: [INTEGRATION.md §5](../INTEGRATION.md#5-degradation) requires an agent to
*refuse* rather than proceed with a stale or unavailable Claude credential. Fail-closed is correct
and, without something here, it means "fail".

This is the last thing standing between the hub and Phase 3's exit criterion. It is a hub-side
decision, and no phase of the roadmap covered it.

## Decision

Add **`POST /auth/agent-grant`**. An agent exchanges a live agent access token, once at run start,
for a longer-lived token that can do exactly one thing: resolve, report and account for a Claude
credential.

```jsonc
{
  "sub": "3",                      // the same user
  "sid": "3a7e…",                  // the same hub session — load-bearing, see below
  "aud": "emehub:grant",           // an INTERNAL audience
  "agt": "qagent",                 // the agent it was minted for
  "scp": "claude-credential",      // the only thing it authorises
  "run": "…",                      // opaque to the hub; audit only
  "iss": "emehub",
  "exp": …                         // EMEHUB_AGENT_GRANT_TTL_MINUTES, default 240, capped 1440
}
```

It reaches `GET /credentials/claude/resolve`, `PUT /credentials/claude/refreshed` and
`POST /credentials/claude/usage`. Nothing else.

### The five properties that make this narrow rather than "a long-lived token"

1. **It cannot be an access token, structurally.** `aud` is `emehub:grant`, in the same
   never-registerable namespace as the existing `emehub:mfa` and `emehub:reset`. So
   `decode_access_token` and `decode_any_registered` both reject it by construction, not by a check
   someone can forget. Presented to `/projects`, `/tickets`, `/me` or `/audit/events`, it is a 401.
2. **Its reach is decided by wiring, not by a claim.** Exactly one dependency
   (`require_credential_grant`) accepts a grant, and exactly one router declares it. The `scp` claim
   is checked as well, so a token in the grant audience *without* a scope is refused rather than
   treated as unscoped — but the wiring is the real boundary, because it cannot be widened by
   forging a claim.
3. **Hub session revocation still kills it, immediately.** The grant carries the same `sid`, and
   `deps_auth._load_principal` performs the same live-session lookup it already performed for access
   tokens. Revoke the session and the next use of the grant is a 401 —
   [INTEGRATION.md §2](../INTEGRATION.md#2-token)'s "revoking the session kills every agent" holds
   verbatim, **and no grant registry, revocation list or new table is needed**. This is the single
   most important property: without it, a grant would be an unrevocable credential.
4. **It cannot renew itself.** Minting requires a live agent *access* token, so
   `POST /auth/agent-grant` is gated on `require_principal` and a grant presented to it is refused.
   There is no grant→grant chain: a leaked grant expires and stops.
5. **Mint and use are both audited.** The mint records the agent and the `runId`; `/resolve` already
   audits every call including misses. So a resolved credential is traceable to the run that asked
   for it.

The lifetime is bounded in code (`GRANT_TTL_CAP_MINUTES = 1440`) and an out-of-range setting is a
**startup failure**, not a silent clamp — an operator who typed minutes meaning hours should find
out immediately, and a hub running with a different lifetime than configured would be worse than one
that refuses to boot.

There is deliberately **no** switch that disables grants. Consistent with `CLAUDE.md` › *Never fail
open*: no configuration turns this into an authentication bypass. An operator who does not want
grants has agents that never ask for one.

## Alternatives considered

**Raise `access_token_ttl_minutes` for agent audiences.** One line, and the reason it was rejected:
it weakens every endpoint's posture to fix one. A multi-hour token that also reaches `/projects`,
`/tickets` and `/connections` is a strictly worse trade than a multi-hour token that reaches only
the credential. It also silently changes the blast radius of every already-issued token.

**Let agents call `/auth/refresh`.** Forbidden for a reason that has not changed: it *rotates*, so
two applications sharing one refresh cookie race and log each other out
([ADR 0008](0008-cross-app-session-handoff.md)).

**Resolve once at run start and hold the material in memory.** The cheapest option and it is what
agents should do *anyway* — but it is not sufficient. A long run can legitimately need to
re-resolve: the CLI rotates its token mid-run (which is why `PUT /credentials/claude/refreshed`
exists), and a run may start work on a second project. "Resolve once or fail" would make those
failures, not features. The grant makes re-resolution legal without making anything else legal.

**A server-to-server hand-off code, redeemed for a fresh token.** More machinery, an extra round
trip, and it ends up minting something long-lived anyway — the grant *is* the redeemed artefact,
without the redemption step.

## Consequences

- Phase 3's agent cutover is unblocked. The remaining work on the credential path is the
  `QAGENT_SECRET_KEY` → `EMEHUB_ENCRYPTION_KEY` re-key, which is agent-side and independent.
- **The hub now issues a token that outlives an access token by up to 96×.** That is the cost, and
  it is paid down by properties 1–3 above rather than by hoping nobody misuses it. The test suite
  asserts the negative cases per route, because they *are* the design.
- `security.auth_guard` had to learn about grants, since it is a deny-by-default backstop that
  otherwise refuses one before any route dependency runs. It only answers "did this hub issue
  this?"; it does not widen what a grant may reach.
- A new router posture, `GRANTED`, exists in `main.ROUTERS` for the one router that accepts grants.
  The blanket dependency has to be the *loosest* one a router needs, since every route's own
  dependency also runs and the stricter one decides — so credential *management* stays hub-only even
  though the router accepts grants.
- Two structural tests that enumerate the accepted guard dependencies had to be updated by hand.
  That friction is intentional: a new auth dependency should not silently satisfy them.
- When Phase 3 moves to RS256 + JWKS, grants move with it for free — they go through the same
  `_encode` / `_decode` and carry the same `kid`.
