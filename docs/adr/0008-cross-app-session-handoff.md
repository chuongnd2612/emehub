# ADR 0008 — Cross-app session hand-off via a shared cookie and a non-rotating mint

- **Status:** Accepted
- **Date:** 2026-08-05

## Context

The hub owns identity, but nothing consumes it. Both Launch affordances in the UI are literal
no-ops (`app/src/screens/Overview/ProductCard.tsx:63`,
`app/src/screens/Landing/ProductCard.tsx:22-36`), and no agent validates a hub token. So the hub
runs *alongside* QAgent rather than in front of it — the outcome
[ADR 0001](0001-emehub-is-the-source-of-truth.md) rejected when it ruled out the launcher option.

Closing that gap needs a mechanism for turning "signed in at the hub" into "signed in at the
agent", without a second login. The deployment target is settled: all three applications are
served from subdomains of one registrable domain behind a cloudflared tunnel
(`hub.chuongnd.click`, `qagent.chuongnd.click`, …).

## Options considered

**(a) Share the refresh cookie and let the agent call `/auth/refresh`.**
The subdomains are same-site, so a `Domain=.chuongnd.click` cookie with `SameSite=Lax` reaches the
hub from the agent's origin, and `allow_credentials` is already on. No new endpoint at all.

**Rejected as written**, for a defect rather than a preference: `POST /auth/refresh` **rotates**
(`api/app/services/auth_service.py:333-344` overwrites `refresh_token_hash`, and
`find_session_by_refresh` is an exact hash lookup, so the previous value dies immediately). Two
SPAs sharing one rotating single-use credential, each running a silent 401→refresh, will race —
whichever lands second presents a dead token and logs out a session the user legitimately held.
Intermittent, user-visible, and not tunable away.

**(b) A short-lived single-use hand-off code, redeemed server-to-server** with a per-agent client
secret. Origin-agnostic, works across unrelated registrable domains, and an agent-side XSS can
mint nothing because redemption needs a secret the browser never holds.

Costs: a `agent_handoff_codes` table and migration, a hand-off service, per-agent client secrets to
generate, distribute and rotate, and — the ongoing one — the agent's *API container* must be able
to reach the hub's API. Across two independent compose stacks that means `host.docker.internal` in
development and real cross-service routing in production.

**(c) The access token in a URL fragment.** Rejected: it lands in `window.history`, is readable by
any script or extension on the agent page, and survives a copied URL. It also buys nothing
structurally — the token lives 15 minutes and the agent may not refresh it, so the agent needs its
own session regardless.

## Decision

**Option (a), with the rotation removed from the agent's path.** Share the refresh cookie on the
common parent domain, and add a dedicated endpoint that mints an audience token **without
rotating**:

```
POST /auth/agent-token   { "audience": "qagent" }
```

It authenticates with the HttpOnly refresh cookie plus the CSRF double-submit — the same way
`/auth/refresh` does, which is why it sits beside it in `PUBLIC_PATHS` — and returns a token for
that audience only, with no refresh material and no `Set-Cookie`. The hub's own audience is
refused, so an agent origin cannot mint credentials for hub-only routes. Every call is audited.

The agent establishes **its own** session from that token, so the hub token is consumed once at
bootstrap rather than held.

## Consequences

**Good.** Far less to build and operate than (b): no code table, no migration, no per-agent
secrets, and — the durable saving — **no container-to-container reachability requirement**, since
the exchange is entirely browser-driven. Because the agent creates its own session, this slice has
no 15-minute-token problem and needs no agent-side refresh mechanism.

**Bad — subdomain trust becomes load-bearing.** XSS on any `*.chuongnd.click` page can call
`/auth/agent-token` and mint agent tokens. `verify_csrf`
(`api/app/services/auth_service.py:408-412`) is a plain double-submit against a *readable* cookie,
which any subdomain can read, so it gives no protection against a same-site attacker. Accepted
because every subdomain is self-hosted and operated by one small team. **This must be revisited if
the suite moves to a domain where other people operate subdomains.**

**Bad — refresh-token reuse detection weakens slightly**, because one path now accepts the token
without rotating it. Mitigated by auditing every call.

**Constraining.** The mechanism only works while the hub and its agents share a registrable
domain. If an agent moves off it, option (b) is the migration path — it is designed above and
deliberately not built.

**Fragile in one specific way.** The value of this design *is* the absence of rotation. Anything
added to `/auth/agent-token` that rotates, re-issues cookies, or invalidates the session
reintroduces exactly the race (a) was rejected for.
`api/tests/test_agent_token.py::test_minting_does_not_rotate_the_refresh_token` is the regression
guard, and it says so in its docstring.

**Deployment requirement.** `EMEHUB_COOKIE_DOMAIN` must be set to the shared parent and each
agent's origin added to `EMEHUB_CORS_ORIGINS`. Note that all `localhost` ports share one cookie
jar, so this flow appears to work in development for the wrong reason and never exercises `Secure`
or real `SameSite` behaviour — it must be verified against the tunnel over HTTPS.
