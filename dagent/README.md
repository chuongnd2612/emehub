# Deploying D-Agent

D-Agent (`ticket-executor`) ships no container assets of its own, so the suite's deployment of it
lives here: an emehub-owned `Dockerfile` and compose project that build the sibling checkout and
run it locally, the way Q-Agent runs.

Nothing in `ticket-executor/` is modified by any of this (CLAUDE.md › Sibling repositories). The
changes D-Agent has to make *itself* are written up in
[docs/DAGENT-HANDOFF.md](../docs/DAGENT-HANDOFF.md) — including taking this Dockerfile over.

```
claude-projects/
  emehub/dagent/                        ← this directory
  ticket-executor/ticket-executor/      ← the build context
```

The layout above is required. Both repos must be siblings on disk or the build has no context.

---

## Bring it up

```bash
docker network create emesoft                              # once, shared with the hub + q-agent
cp dagent/.env.example dagent/.env                         # then fill in the two required values
docker compose -f dagent/docker-compose.yml up -d --build
```

`dagent/.env` needs `DAGENT_APP_ACCESS_PASSWORD` and `DAGENT_SETTINGS_ENC_KEY`. The container
**refuses to start** without them — stricter than D-Agent's own defaults, because both of its
fallbacks (no auth gate at all; encryption key derived from `DATABASE_URL`) are wrong for something
that publishes a port and pushes commits.

Then open **http://127.0.0.1:5190/dagent** — the suite's front door — and sign in with the password
you set. The container also publishes 3000, but a `DAGENT_BASE_PATH` build serves nothing at the
root of that port: direct access is `http://localhost:3000/dagent`.

Migrations apply on every start (`prisma migrate deploy`), so a schema change in the sibling repo
needs a rebuild, not a manual step.

## Verifying

```bash
docker compose -f dagent/docker-compose.yml ps                     # both services healthy
curl -s -o /dev/null -w '%{http_code}\n' http://localhost:3000/login       # 200
curl -s -o /dev/null -w '%{http_code}\n' http://localhost:3000/api/settings # 401 — the gate is on
```

A `200` on that last one means `APP_ACCESS_PASSWORD` did not reach the app and the auth gate has
disabled itself. Stop the stack rather than leaving it up.

## Launching it from the hub

D-Agent is mounted at **`/dagent` on the suite's shared origin**, the way q-agent is mounted at
`/qagent` ([ADR 0010](../docs/adr/0010-one-origin-for-the-suite.md)). Press `Launch` on the hub's
Overview card and the address bar goes to `<origin>/dagent` — no second hostname, no CORS entry, and
no cookie-domain question, because a same-origin path is hand-off-ready by construction.

In `emehub/.env`:

```
EMEHUB_AGENT_DAGENT_URL=/dagent
```

then `docker compose up -d` in the hub. Check it took:

```bash
docker compose exec -T api python -c "from app.config import settings as s; print(s.agent_url('dagent'), s.handoff_ready('dagent'), s.handoff_blocker('dagent'))"
# /dagent True None
```

Verify the mount end to end:

```bash
curl -s -o /dev/null -w '%{http_code}
' http://127.0.0.1:5190/dagent          # 200
curl -s -o /dev/null -w '%{http_code}
' http://127.0.0.1:5190/dagent/dashboard # 307 -> /dagent/login
curl -s -o /dev/null -w '%{http_code}
' http://127.0.0.1:5190/dagent/api/settings # 401
curl -s -o /dev/null -w '%{http_code}
' http://127.0.0.1:5190/api/health       # 200, hub untouched
```

A `Launch` that lands on D-Agent's own login form is correct today: the mount carries *navigation*,
not single sign-on. D-Agent does not yet exchange a hub token for a session
([handoff §4](../docs/DAGENT-HANDOFF.md)), and the hub is not the side that can finish that.

### How the mount works, and what is a workaround

Three pieces, and two of them should not be permanent.

1. **`basePath=/dagent`, compiled in.** `dagent/Dockerfile` takes `DAGENT_BASE_PATH` as a build arg
   and re-exports D-Agent's own `next.config.ts` through a wrapper that adds the key. Changing the
   prefix is a **rebuild**, not a restart, and it must agree with the edge block and
   `EMEHUB_AGENT_DAGENT_URL`. Setting `DAGENT_BASE_PATH=` (empty) builds the app for its own origin
   again, unchanged.
2. **The prefix is passed through, not stripped** — the opposite of q-agent's block, because the Next
   server expects it. Note that Next canonicalises `/dagent/` to `/dagent`, so the edge must *not*
   redirect the bare form to the slashed one: that is an infinite redirect, and it is how this was
   first found.
3. **Two patches in `edge/nginx.conf`** — a `proxy_redirect` because D-Agent's auth gate builds its
   login redirect with `new URL("/login", request.url)`, which drops the basePath; and a small
   injected shim that prefixes root-relative `fetch`/`XHR`/`EventSource` URLs, because `basePath`
   does not rewrite string literals and D-Agent's client code has ~48 `fetch("/api/…")` calls that
   would otherwise hit **the hub's** API.

Piece 3 is patching another repo's code from a proxy. It works — verified in a browser, with every
API call on every page landing under `/dagent/api` and none on the hub's — and it is still a
workaround with an expiry date: when D-Agent ships an `apiFetch()` helper and reads `basePath` from
its own config ([handoff §2](../docs/DAGENT-HANDOFF.md), ticket-executor#93), both patches are
deleted and only the proxy remains.

### One known gap the mount introduces

`proxy.ts` matches on `/((?!_next/static|_next/image|favicon.ico).*)`, and under a basePath the bare
`/dagent` arrives with an **empty** pathname, which that pattern does not match. So the app's root
route — a static landing page, `Ship tickets, not busywork` — renders without the auth gate. Every
other page still redirects to `/dagent/login` and every `/dagent/api/*` route still answers 401, so
no data is exposed; but it is a gate that stops applying to one route, which is not something to
leave unsaid. The fix is one entry in D-Agent's matcher (handoff §2).

### Hub mode needs the public hub URL

`DAGENT_HUB_URL` is used for two different things — D-Agent's server-side reads *and* the value the
browser mints its token against — and D-Agent has only the one variable for both (q-agent splits it
into public and internal). So it must be the **browser-reachable** URL, including the hub's `/api`
prefix:

```
DAGENT_HUB_URL=https://hub.<domain>/api
```

A *relative* `/api` is wrong here: the shim in the edge block would prefix it to `/dagent/api`.

D-Agent now splits the two, so the server side no longer has to share the browser's URL:

```
DAGENT_HUB_URL_INTERNAL=http://emehub-web:5180/api
```

Empty falls back to `DAGENT_HUB_URL`, which is right for a public deployment where one URL serves
both sides. It matters on a laptop: `DAGENT_HUB_URL` is then `http://localhost:5180/api`, and inside
this container `localhost` is *the container*, so the browser mints a token successfully and every
server-side read that follows fails with "EmeHub is unreachable".

Because the mount puts D-Agent on the hub's own origin, that mint is now a same-origin request —
so hub mode works when you browse the suite at `https://hub.<domain>/dagent`, and not when you
browse the container directly at `http://localhost:3000`.

## What a containerised run can do

D-Agent's purpose is to spawn the Claude Code CLI inside a git repository. The image carries `git`,
the CLI, and the four skills a run drives (pre-installed at `/root/.claude/skills`, because a
missing skill fails partway into a run rather than up front). Two things it cannot carry:

**A Claude credential.** Two ways, and the first is much better in a container:

- *Hub mode.* Turn **Part of EmeHub** on in D-Agent's Settings. Every run then resolves its
  credential from the hub and materialises it for that run only
  (`lib/claudeConfig.ts`, `lib/hubCredential.ts`), with no login on this machine and rotated tokens
  posted back — the arrangement [INTEGRATION.md §4](../docs/INTEGRATION.md) describes. It needs
  `DAGENT_HUB_URL` set *and* a hub session, which the Settings page mints in the browser. That mint
  is a cross-origin POST carrying the hub's cookie, so it works from D-Agent's registered origin and
  **not** from `http://localhost:3000` — the hub's cookie is scoped to its domain, and the browser
  will not send it to a bare loopback origin.
- *Its own login,* for hub mode off. Interactive, once; it persists in the `dagent-claude` volume:

  ```bash
  docker compose -f dagent/docker-compose.yml exec dagent-web claude
  ```

**The repository itself.** A run's working directory is the ticket's *Root repo* value verbatim, so
a host path like `C:\repos\my-service` means nothing inside the container. Clone into the
`dagent-repos` volume and use the container path:

```bash
docker compose -f dagent/docker-compose.yml exec dagent-web git clone <url> /repos/my-service
# then set Root repo = /repos/my-service on the ticket's Overview tab
```

`git push` must work non-interactively from in there — a run cannot answer a credential prompt.
Verify by hand with `git -C /repos/my-service push --dry-run` before spending tokens on a run.

Until both are done the app is fully usable for browsing tickets, projects and settings; it is the
*Implement* / *Resolve Review* actions that need them. D-Agent's own **System Check** page is the
thing to trust about all of it — as of `ticket-executor@62bba10` its deep probe verifies that the
credential actually authenticates, rather than reporting the hub's status string.

## Stopping, and what persists

```bash
docker compose -f dagent/docker-compose.yml down          # keeps all three volumes
docker compose -f dagent/docker-compose.yml down -v       # deletes run history, repos, credential
```

Three volumes: `dagent-db` (settings, executions, the encrypted PAT), `dagent-repos` (clones), and
`dagent-claude` (**the plaintext Claude credential** — treat it like the hub's workspace volume,
[ADR 0007](../docs/adr/0007-knowledge-builds-run-on-the-hub.md); not a mount to copy around).
