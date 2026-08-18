# The suite's front door

One origin for hub + agents, so the suite reads as one product rather than three sites that
redirect to each other. See [ADR 0010](../docs/adr/0010-one-origin-for-the-suite.md) for why.

```
app.<domain>
  /            -> emehub SPA
  /api/*       -> emehub API
  /qagent/*    -> q-agent SPA, its /api and its /auth
  /dagent*     -> D-Agent (Next), prefix passed through rather than stripped
```

**The two agents get here differently, and the difference matters when editing `nginx.conf`.**
q-agent is a static bundle, so its prefix is *stripped* and its own nginx never learns the mount
exists. D-Agent is a Next server built with `basePath=/dagent` ([`dagent/README.md`](../dagent/README.md)),
so its prefix is *passed through* — the server expects it on every request.

D-Agent's block also carries two patches for things `basePath` does not cover: its auth gate's
redirect loses the prefix, and ~48 root-relative `fetch("/api/…")` calls in its client code would
otherwise resolve to the hub's API. Both are workarounds for another repo's code and both are
deleted when D-Agent ships the real fix
([docs/DAGENT-HANDOFF.md §2](../docs/DAGENT-HANDOFF.md), ticket-executor#93). They are commented in
place; read them before changing that block.

## Cutting over

Nothing here is switched on by default. Each step is reversible, and the old hostnames keep
working throughout.

**1. Create the shared network** (once):

```bash
docker network create emesoft
```

**2. Point q-agent at its mount path** — `q-agent/.env`:

```
QAGENT_BASE_PATH=/qagent
QAGENT_HUB_BASE_URL=/api      # the hub's API on the SHARED origin, for the browser
```

`QAGENT_BASE_PATH` drives both halves: the frontend build arg (`VITE_BASE`) and the backend's
`QAGENT_MOUNT_PATH`, which sets cookie `Path`. They must agree — a mismatch scopes the refresh
cookie to a path the browser never requests, and the session silently ends at the next reload.

Leave `QAGENT_HUB_INTERNAL_BASE_URL` as it is: server-side reads should stay on the local bridge
whatever the browser does.

**3. Point the hub at the agent's path** — `emehub/.env`:

```
EMEHUB_AGENT_QAGENT_URL=/qagent
```

Once every consumer is on the shared origin you can also empty `EMEHUB_CORS_ORIGINS` and
`EMEHUB_COOKIE_DOMAIN` — both exist only because the apps were on different hosts. Empty the
cookie domain **last**: `_purge_other_scope` needs one pass to clear the old domain-wide cookies
out of browsers that signed in under the subdomain model.

**4. Rebuild and start:**

```bash
cd q-agent && docker compose up -d --build
cd ../emehub && docker compose up -d --build
docker compose -f edge/docker-compose.yml up -d
```

**5. Add the tunnel ingress.** The tunnel is remotely managed (`cloudflared … --token`), so this is
a Cloudflare Zero Trust dashboard change, not a repo one: point `app.<domain>` at
`http://localhost:5190`. Repoint `hub.<domain>` at the same place if you want the old hub URL to
keep working — the edge serves the hub at `/`, so it will.

**Do not repoint `qagent.<domain>`.** It must keep reaching q-agent's own web container directly,
because paired Local Agents persist that URL in `~/.qagent-agent/config.json` and read their
auto-update feed from a file inside the installed app. Neither can be told otherwise from the
server, so a device that loses that host needs re-pairing by hand.

## Verifying

```bash
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:5190/api/health
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:5190/qagent/api/health
curl -s -o /dev/null -w '%{http_code}\n' https://qagent.<domain>/downloads/latest.yml
```

Then in a browser: sign in at `/`, press Launch, and confirm you land **authenticated** on
`/qagent/` with the address bar unchanged. If you land on `/qagent/login` instead, the hand-off did
not carry — check that `QAGENT_HUB_BASE_URL` is the shared-origin `/api` and not a public URL.

## Reverting

Clear `QAGENT_BASE_PATH`, restore `QAGENT_HUB_BASE_URL` and `EMEHUB_AGENT_QAGENT_URL` to public
origins, rebuild both stacks, and `docker compose -f edge/docker-compose.yml down`. The per-app
hostnames were never taken away, so there is nothing else to put back.
