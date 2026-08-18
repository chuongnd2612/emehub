# Handoff to D-Agent — deployment

**Audience:** whoever works on `ticket-executor` (`DaoLinh98/ticket-executor`).
**Written from:** the hub, while deploying D-Agent as a container in the suite (emehub #161).

D-Agent now runs in a container and the hub's `Launch` button reaches it. Everything needed for
that was done on the hub side — the image is built from an emehub-owned `Dockerfile`
([`emehub/dagent/`](../dagent/README.md)) against the `ticket-executor` checkout as build context,
and nothing in `ticket-executor/` was touched (CLAUDE.md › Sibling repositories).

This document is the list of things that **cannot** be done from the hub side. None of them block
the deployment as it stands; each one removes a limitation the deployment currently works around.

| § | What | Why it needs D-Agent |
|---|---|---|
| 1 | Own the container image | The Dockerfile tracks D-Agent's layout from another repo |
| 2 | A shared-origin mount (`/dagent`) | `basePath` + ~48 root-relative `fetch("/api/…")` calls |
| 3 | Remove the auth fail-open | `authDisabled()` lives in `lib/auth.ts` |
| 4 | Consume a hub token as a session | The hand-off carries identity D-Agent does not read |
| 5 | A health endpoint | The container healthcheck currently probes `/login` |
| 6 | Runs inside a container | Repo paths and the Claude credential are host-shaped |

---

## 1. Own the container image

`emehub/dagent/Dockerfile` and `emehub/dagent/docker-compose.yml` are a deliberate stopgap. They
are correct today and they are in the wrong repository: they name D-Agent's source directories,
its start command and its migration tool, so any restructuring in `ticket-executor` breaks a build
defined somewhere its author cannot see.

Moving them across is mostly a copy. Three things get *better* once they live in D-Agent, because
each needs a file in the app's own root:

- **A `.dockerignore`.** `.dockerignore` is resolved from the build-context root, which today
  belongs to `ticket-executor`, so the hub-side Dockerfile cannot have one. It works around that by
  copying source directories one by one (`COPY app ./app`, `COPY lib ./lib`, …) rather than
  `COPY . .` — otherwise a developer's Windows-built `node_modules/` and stale `.next/` would be
  copied over the Linux ones installed in the image, and the resulting crash (a Prisma query engine
  or Next SWC binary for the wrong platform) looks like anything but a Docker problem.
- **`output: "standalone"` in `next.config.ts`.** The image currently ships the full
  `node_modules` — including dev dependencies, because `prisma migrate deploy` runs from the Prisma
  CLI at container start. Standalone output plus a copied-in Prisma CLI would cut it substantially.
- **Not needing a placeholder `DATABASE_URL` at build time.** Prisma requires the variable to be
  *set* for `prisma generate`/`next build`, so the hub-side Dockerfile passes a throwaway value on
  that one `RUN`. Nothing connects during the build; it is noise that belongs next to the schema.

When you take it over, tell the hub — `emehub/dagent/` should then be deleted, not left to rot as a
second definition of the same image.

## 2. A shared-origin mount at `/dagent`

Q-Agent is served as a path on the suite's single origin (`/qagent`, [ADR 0010](adr/0010-one-origin-for-the-suite.md));
D-Agent is served from its own origin instead. That asymmetry is not a preference — the front door
cannot mount D-Agent as it is.

**Why Q-Agent's arrangement does not transfer.** Q-Agent's frontend is a static Vite bundle:
`VITE_BASE=/qagent/` changes the URLs it *emits*, the edge strips the `/qagent` prefix, and
Q-Agent's own nginx keeps seeing exactly the paths it always saw. D-Agent is a Next *server*.
Mounting it under a prefix means `basePath`, and then the server expects that prefix on every
request — so the edge must pass it through rather than strip it. Next handles its pages, its assets
and its route handlers under that prefix by itself.

What it does not handle is client code. There are ~48 root-relative fetches across 14 files
(`fetch("/api/settings")`, `fetch("/api/dashboard?…")`, `app/hubSession.ts`, `app/login/page.tsx`, …).
Next does not rewrite string literals, so under `basePath` every one of them resolves to
`https://<origin>/api/…` — which on the shared origin is **the hub's API**, not D-Agent's. The
symptom would be a UI that loads and then 401s or 404s on everything.

The change:

1. A single client helper — `apiUrl(path)` or a thin `apiFetch()` — that prefixes the base path, and
   every root-relative `fetch` routed through it. This is the bulk of the work and it is mechanical.
2. `basePath` in `next.config.ts`, from an env var so standalone deployment stays possible
   (Q-Agent's equivalent is `QAGENT_BASE_PATH`, driving both halves of its build).
3. The auth cookie's `Path` scoped to the mount path. Q-Agent learned this one the hard way: a
   cookie scoped to a path the browser never requests makes the session end silently at the next
   reload.
4. `proxy.ts`: verify the gate still matches. `PUBLIC_PATHS` compares `nextUrl.pathname` against
   literals (`/login`, `/api/auth/login`), and the redirect builds `new URL("/login", request.url)`
   — check against a real `basePath` build whether the prefix is present or stripped in each, rather
   than reasoning about it. Getting this wrong either opens the gate or produces a redirect loop.

The hub side is already prepared: `docker-compose.yml` attaches D-Agent to the `emesoft` network
with the alias **`dagent-web`**, which is the upstream name `edge/nginx.conf` will use. When the
above lands, the hub adds one location block and sets `EMEHUB_AGENT_DAGENT_URL=/dagent` — a
same-origin path is hand-off-ready by construction, so it needs no cookie domain and no CORS entry
at all.

## 3. Remove the auth fail-open

Unchanged from [INTEGRATION.md § 6.1](INTEGRATION.md#61-dagents-auth-gate-disables-itself), and now
sharper, because D-Agent publishes a port: `authDisabled()` in `lib/auth.ts` returns true when
`APP_ACCESS_PASSWORD` is empty, and `proxy.ts` then lets every request through — pages and API alike
— for an application that commits, pushes and opens pull requests with
`--dangerously-skip-permissions`.

The hub-side deployment refuses to *start* without a password (`:?` on
`DAGENT_APP_ACCESS_PASSWORD`), which is a guard on one deployment, not a fix. It must be
**removed**, not supplemented: validation added alongside a switch that turns authentication off
leaves the off switch in production.

## 4. Consume a hub token as a session

The hub mints tokens for the `dagent` audience and, with `EMEHUB_AGENT_DAGENT_URL` set to an origin
under `EMEHUB_COOKIE_DOMAIN`, `GET /agents` reports D-Agent `handoffReady`. What that buys today is
*navigation*: pressing `Launch` on the hub's Overview card lands on D-Agent — at D-Agent's own login
form, because nothing there exchanges the hub session for a local one.

D-Agent already talks to the hub as a client (`lib/hub.ts`, `lib/hubGateway.ts`,
`lib/hubCredential.ts` call `/dagent/connections` and `/credentials/claude/*`), so the token
plumbing exists. What is missing is the browser-side bootstrap Q-Agent implemented: on first load
without a local session, `POST <hub>/auth/agent-token` with credentials, and accept the resulting
`aud: "dagent"` token as the session instead of redirecting to `/login`. See
[ADR 0008](adr/0008-cross-app-session-handoff.md), [INTEGRATION.md § 2](INTEGRATION.md), and
q-agent's `docs/HUB-INTEGRATION.md` as the worked example.

Two hub-side prerequisites are already in place for
[the current deployment](../dagent/README.md#launching-it-from-the-hub): the agent URL is
registered, and D-Agent's origin is in `EMEHUB_CORS_ORIGINS` so that cross-origin POST is allowed
with credentials.

Ordering note from INTEGRATION.md § 6.2, still worth keeping: hub *identity* and hub *credentials*
are separate milestones and should not be bundled into one issue.

## 5. A health endpoint

There is no `/api/health`, so the container healthcheck probes `/login` — the one route that answers
200 without a session whatever the auth gate is doing. It works, and it is indirect: it cannot
distinguish "Next is up" from "Next is up and Postgres is reachable", so a database the app cannot
talk to still reports healthy.

A trivial `app/api/health/route.ts` returning 200 after a `SELECT 1` through Prisma would make the
healthcheck mean something, and would let `depends_on: condition: service_healthy` be trusted by
anything placed in front of D-Agent later.

## 6. Runs inside a container

D-Agent was written as a developer tool on a developer's machine, and two of its assumptions are
host-shaped. Both are documented as operator steps in
[`dagent/README.md`](../dagent/README.md#what-a-containerised-run-can-do); neither can be fixed from
the hub.

**Repository paths.** A run's working directory is the ticket's *Root repo* value verbatim, so
`C:\repos\my-service` — a perfectly good value on the host — means nothing inside the container.
The deployment provides a `dagent-repos` volume at `/repos` and the operator clones into it by hand,
then types the container path. Worth considering on your side: a configured repository *root* that
Root repo is resolved against, or a clone-on-demand step, so the field stops being a host path
pasted into a container.

**The Claude credential.** `lib/execution/claudeCli.ts` shells out to whatever `claude` is logged in
where the app runs. In a container that is the container's own `/root/.claude`, so the deployment
persists it as a volume and the operator authenticates once with
`docker compose exec dagent-web claude`. You already have `lib/hubCredential.ts` reading the hub's
`/credentials/claude/resolve`, so the better path may already be half-built — worth verifying
whether a containerised run can materialise the hub credential and skip the interactive step
entirely. The hub's `api/app/services/claude_credentials.py::materialize`
([ADR 0007](adr/0007-knowledge-builds-run-on-the-hub.md)) is a worked example.

Also unchanged and still an open product question from INTEGRATION.md § 6.2:
`--dangerously-skip-permissions` is defensible for a single-developer local tool and indefensible
for a multi-user service. Containerising D-Agent does not decide that, but it does make the question
easier to stop noticing.

---

## What the hub did, for reference

Nothing here needs action; it is what your side is now sitting behind.

- `dagent/Dockerfile`, `dagent/docker-compose.yml`, `dagent/.env.example`, `dagent/README.md` —
  the image and a two-service stack (`dagent-web` + `dagent-db`), on the shared `emesoft` network
  with the alias `dagent-web`, published on host port 3000, database on 5458.
- Migrations applied at container start with `prisma migrate deploy` (never `migrate dev` — deploy
  stops on drift instead of resetting the database).
- `APP_ACCESS_PASSWORD` and `SETTINGS_ENC_KEY` promoted to hard start-up requirements for this
  deployment; see § 3 for why that is not the fix.
- `EMEHUB_AGENT_DAGENT_URL` pointed at D-Agent's origin and that origin added to
  `EMEHUB_CORS_ORIGINS`, so `GET /agents` reports D-Agent registered and hand-off-ready and the
  Overview card's button is live.
- The Overview product card's `live` flag flipped from `false` to `true`: it read "Placeholder" for
  an application that is now deployed and reachable.
