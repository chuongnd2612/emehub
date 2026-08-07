# ADR 0010 — One origin for the suite, with agents mounted on paths

- **Status:** Accepted
- **Date:** 2026-08-07
- **Supersedes:** the deployment premise of [ADR 0008](0008-cross-app-session-handoff.md). The
  hand-off *mechanism* ADR 0008 chose is unchanged and still correct.

## Context

ADR 0008 recorded the deployment target as settled: "all three applications are served from
subdomains of one registrable domain behind a cloudflared tunnel". Everything about the sign-in
hand-off follows from that — the `Domain=.chuongnd.click` cookie, `EMEHUB_CORS_ORIGINS`, and a
cross-origin `POST /auth/agent-token` from the agent's browser.

Two things have since made the premise worth revisiting.

**It does not read as one product.** The hub's Launch button is a `window.location.assign` to
another origin. The user watches the address bar change and lands somewhere that looks related but
plainly is not the same place. The suite is one product presented as three sites.

**The shared cookie is broader than anyone intended.** `Domain=.chuongnd.click` is sent to *every*
subdomain, so the hub's refresh cookie is transmitted to `dev.chuongnd.click` — a separate
application, with its own Supabase auth, that has no business receiving it. ADR 0008 accepted "XSS
on any `*.chuongnd.click` page can call `/auth/agent-token` and mint agent tokens" and said it must
be revisited if the domain ever hosted anything else. It does.

## Decision

**One origin, with the hub as the shell at `/` and each agent mounted under a path prefix.**

```
app.<domain>
  /            -> emehub SPA   (its own screens already live under /app)
  /api/*       -> emehub API
  /qagent/*    -> q-agent SPA, its /api and its /auth
  /dagent/*    -> reserved
```

A single nginx front door (`edge/`) routes by prefix and **strips it**, so each app's own nginx is
untouched and keeps seeing exactly the paths it sees standalone. Each app is *built* knowing its
mount point (q-agent's `VITE_BASE`), because asset URLs are baked in and nothing downstream can
rewrite them.

Two consequences for the hand-off:

- `POST /auth/agent-token` **stays**. It is now a same-origin call, so no CORS entry and no cookie
  `Domain` are required — but the audience separation, the non-rotation property and the audit
  record are all origin-independent and still doing their jobs.
- `Settings.handoff_ready` learns that a same-origin path is not a degenerate case of the subdomain
  rule but the *strongest* form of it: a same-origin request always carries the cookie. It had been
  a pure hostname-suffix test, which reported `domain_mismatch` for `/qagent` and would have
  disabled the Launch button permanently.

**The old hostnames stay in the tunnel.** `qagent.chuongnd.click` keeps serving `/api` and
`/downloads/` against the same containers, because paired Local Agents persist the URL they were
paired with in `~/.qagent-agent/config.json` and read their auto-update feed from a file *inside*
the installed app. There is no server-push that can rewrite either. Only UI paths redirect.

## Consequences

**Good.** The suite reads as one product. CORS disappears from production. The refresh cookie goes
back to host-only, so it stops reaching `dev.chuongnd.click` and any future subdomain. And the
constraint ADR 0008 called out — "the mechanism only works while the hub and its agents share a
registrable domain" — becomes weaker still, since same-origin needs no domain relationship at all.

**A trade, not a free win.** Hub and q-agent lose the browser-origin boundary *between them*: same
origin means one `localStorage`, one cookie jar, and no same-origin-policy barrier separating the
two bundles. The set of pages that can mint an agent token shrinks from "any subdomain, forever" to
"this one origin", which is a net reduction — but it is a reduction, not an elimination, and
`verify_csrf` now matters *more* rather than less, because `SameSite=Lax` no longer sits between
the two SPAs.

**Migration is additive.** Nothing breaks at switch-over: the new hostname is added, the old ones
keep answering. Reverting is one environment variable and a rebuild.

**A new coupling.** Each agent's mount point exists in two places that must agree — the frontend
build arg and the backend's cookie-path setting. They are named to match (`QAGENT_BASE_PATH` drives
both in compose) and the failure mode is documented where each is defined, because a mismatch scopes
the refresh cookie to a path the browser never requests and the session silently ends at the next
reload.

**Deployment requirement.** The tunnel ingress is remotely managed, so adding the new hostname is a
dashboard change, not a repo change.
