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

Then open **http://localhost:3000** and sign in with the password you set.

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

The hub's Overview card gets a working `Launch` only when `GET /agents` reports D-Agent both
*registered* and *handoff-ready* — a URL alone is not enough, because single sign-on needs the
refresh cookie to reach D-Agent's origin ([ADR 0008](../docs/adr/0008-cross-app-session-handoff.md)).
So the origin has to sit under `EMEHUB_COOKIE_DOMAIN`.

In `emehub/.env`:

```
EMEHUB_AGENT_DAGENT_URL=https://dagent.<domain>
EMEHUB_CORS_ORIGINS=…,https://dagent.<domain>
```

then `docker compose up -d` in the hub to pick it up. Check it took:

```bash
docker compose exec -T api python -c "from app.config import settings as s; print(s.handoff_ready('dagent'), s.handoff_blocker('dagent'))"
# True None
```

The last step is **outside this repo**: add a tunnel ingress for `dagent.<domain>` pointing at
`http://localhost:3000`. The tunnel is remotely managed (`cloudflared … --token`), so that is a
Cloudflare Zero Trust dashboard change, exactly like the one `edge/README.md` describes for the
front door.

Pressing `Launch` then navigates to D-Agent, and D-Agent's own login is reached — the hand-off
carries the *hub session*, but D-Agent does not yet consume a hub token to sign a browser in
([handoff § 2](../docs/DAGENT-HANDOFF.md)). Navigation is live; single sign-on is not, and the hub is
not the side that can finish it.

### Why not `/dagent` behind the suite's front door

Q-Agent is mounted as a path on the shared origin (`/qagent`), and D-Agent is not, which looks like
an oversight. It isn't:

- Q-Agent's frontend is a static Vite bundle. `VITE_BASE=/qagent/` changes the URLs it *emits*;
  the edge strips the prefix and Q-Agent's nginx sees exactly the paths it always saw.
- D-Agent is a Next server. Mounting it under a prefix means `basePath`, which the *server* then
  expects on every request — and Next does not rewrite the ~48 root-relative `fetch("/api/…")`
  calls in D-Agent's client code. Those would resolve against the shared origin and land on the
  hub's `/api` instead of D-Agent's.

That is a change inside D-Agent ([handoff § 1](../docs/DAGENT-HANDOFF.md)), so until it lands
D-Agent gets its own origin. `docker-compose.yml` already attaches it to the `emesoft` network as
`dagent-web`, which is the name `edge/nginx.conf` will need on the day the mount becomes possible.

## What a containerised run can do

D-Agent's purpose is to spawn the Claude Code CLI inside a git repository. The image carries `git`
and the CLI, but a run needs two things that cannot be baked into an image:

**A logged-in Claude credential.** Authenticate once — it persists in the `dagent-claude` volume:

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
*Implement* / *Resolve Review* actions that need them.

## Stopping, and what persists

```bash
docker compose -f dagent/docker-compose.yml down          # keeps all three volumes
docker compose -f dagent/docker-compose.yml down -v       # deletes run history, repos, credential
```

Three volumes: `dagent-db` (settings, executions, the encrypted PAT), `dagent-repos` (clones), and
`dagent-claude` (**the plaintext Claude credential** — treat it like the hub's workspace volume,
[ADR 0007](../docs/adr/0007-knowledge-builds-run-on-the-hub.md); not a mount to copy around).
