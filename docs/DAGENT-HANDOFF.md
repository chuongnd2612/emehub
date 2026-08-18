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
| 2 | Retire the mount's two proxy patches | the mount works, on patches only this repo can remove |
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

## 2. Take the `/dagent` mount off its two proxy patches

D-Agent **is** now mounted at `/dagent` on the suite's shared origin, alongside q-agent's `/qagent`.
It works — verified in a browser, every API call on every page landing under `/dagent/api` and none
on the hub's. It works because the hub side compiles in a `basePath` and then patches two things
from nginx that `basePath` does not cover, and those patches are what this section is asking you to
make unnecessary.

**Why q-agent's arrangement did not transfer.** q-agent's frontend is a static Vite bundle:
`VITE_BASE=/qagent/` changes the URLs it *emits*, the edge strips the prefix, and q-agent's own
nginx keeps seeing exactly the paths it always saw. D-Agent is a Next *server*, so the prefix is
`basePath` and the server expects it on every request — the edge passes it through instead of
stripping it, which is why the two location blocks in `edge/nginx.conf` look nothing alike.

### What the hub currently does on your behalf

1. **`basePath` by wrapper.** `dagent/Dockerfile` renames `next.config.ts` and re-exports it through
   a generated wrapper that adds `basePath`, from a build arg. Additive rather than a patch, but it
   is still this repo compiling your config, and it assumes a default export.
2. **A `proxy_redirect` for the login redirect.** `proxy.ts` sends unauthenticated page requests to
   `new URL("/login", request.url)`, and a plain `URL` built that way **drops the basePath** — the
   app answers `Location: /login`, which on the shared origin is the *hub's* login screen. nginx
   rewrites the header. Using `request.nextUrl.clone()` (a `NextURL`, which re-applies basePath)
   instead of `new URL(…, request.url)` fixes it at the source.
3. **An injected fetch shim.** `basePath` prefixes what the framework emits; it does not touch string
   literals, and there are ~48 root-relative `fetch("/api/…")` calls across 14 files plus one
   `new EventSource("/api/executions/…/stream")`. Without help, every one resolves to the hub's
   `/api`. The edge injects a script into `<head>` that prefixes root-relative `fetch`, `XHR` and
   `EventSource` URLs before they leave the page.

Point 3 is the one that should not last. A proxy rewriting another application's client code is
invisible from inside that application: someone adding a new `fetch("/api/…")` in this repo will
have it silently work in the suite and fail anywhere else, and someone debugging a URL in DevTools
will see a path no source file contains.

### The change that retires them

1. One client helper — `apiUrl(path)` / `apiFetch()` — with every root-relative `fetch` and the
   `EventSource` routed through it. Mechanical, and the bulk of the work.
2. `basePath` in your own `next.config.ts`, from an env var (q-agent's equivalent is
   `QAGENT_BASE_PATH`, driving both halves of its build). The hub's build arg then goes away.
3. `proxy.ts`: build the login redirect from `request.nextUrl`, and add `"/"` to the matcher — see
   the gap below.
4. Scope the `te_session` cookie's `Path` to the mount when one is set. It is `/` today, which
   happens to work under a prefix; it stops being accidental once the mount is a real setting.

Tell the hub when it lands and `edge/nginx.conf` loses both patches in the same PR.

### A gap the mount exposed

`proxy.ts` matches `/((?!_next/static|_next/image|favicon.ico).*)`, and under a basePath the bare
`/dagent` arrives with an **empty** pathname — which that pattern does not match. The app's root
route therefore renders **without the auth gate**. It is the static landing page, every other page
still redirects and every `/api/*` route still answers 401, so nothing is exposed; but it is a gate
that quietly stopped applying to a route, and it would apply to any future public-facing root
content too. `matcher: ["/", "/((?!_next/static|_next/image|favicon.ico).*)"]` closes it.

### A second variable for the hub URL

`DAGENT_HUB_URL` is read for two different jobs: your server-side hub reads, and the value the
browser mints its token against. One variable cannot be right for both — the fast internal address
(`http://host.docker.internal:8790`) is unreachable from a browser, and a relative `/api` is caught
by the shim above. The deployment therefore sets the public URL and eats a tunnel round trip on
every server-side read (~500ms against ~2ms, measured on q-agent). q-agent solved this with
`QAGENT_HUB_BASE_URL` plus `QAGENT_HUB_INTERNAL_BASE_URL`; the same split here would pay for itself.

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

The hub mints tokens for the `dagent` audience, and with the `/dagent` mount `GET /agents` reports
D-Agent `handoffReady` — a same-origin path needs no cookie domain and no CORS entry at all. What
that buys today is *navigation*: pressing `Launch` on the hub's Overview card lands on D-Agent — at
D-Agent's own login form, because nothing there exchanges the hub session for a local one.

D-Agent already talks to the hub as a client (`lib/hub.ts`, `lib/hubGateway.ts`,
`lib/hubCredential.ts` call `/dagent/connections` and `/credentials/claude/*`), so the token
plumbing exists. What is missing is the browser-side bootstrap Q-Agent implemented: on first load
without a local session, `POST <hub>/auth/agent-token` with credentials, and accept the resulting
`aud: "dagent"` token as the session instead of redirecting to `/login`. See
[ADR 0008](adr/0008-cross-app-session-handoff.md), [INTEGRATION.md § 2](INTEGRATION.md), and
q-agent's `docs/HUB-INTEGRATION.md` as the worked example.

The mount makes this easier than it was: `POST {hub}/auth/agent-token` from a D-Agent page is now a
**same-origin** request, so the hub's cookie is sent without a widened `Domain` and without a CORS
entry. That is the strongest form of the ADR 0008 arrangement, not a degenerate one.

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

**The Claude credential.** This one is largely *solved* on your side already, and the container is
where it pays off. With hub mode off, `lib/execution/claudeCli.ts` shells out to whatever `claude` is
logged in where the app runs — in a container, the container's own `/root/.claude`, so the deployment
persists that as a volume and the operator authenticates interactively once. With **Part of EmeHub**
on, `lib/claudeConfig.ts` materialises the hub-resolved credential per run into
`~/.ticket-executor/claude-config/<source>` and points `CLAUDE_SECURESTORAGE_CONFIG_DIR` at it, the
runner refuses a run whose credential cannot authenticate, and `62bba10` made System Check verify
that for real. No login on the box at all.

So the containerised recommendation is hub mode, and the remaining friction is not credentials but
reaching the hub: the session that authorises `/credentials/claude/resolve` is minted **in the
browser** from the hub's cookie, which means D-Agent has to be served from an origin the hub's cookie
reaches. From `http://localhost:3000` it never is. Worth knowing when someone reports that hub mode
"works on my machine but not in the container" — the difference is the origin, not the container.

One gap the container exposed, small but ours to name: the four skills a run drives are installed
into `~/.claude/skills` by the Settings-page installer, and a fresh container has none, so a run
fails partway in with `Unknown command: /implement-ticket-v3` after spending tokens. The hub-side
image pre-installs them from `skills/`. A first-run check — or installing them on boot when the
directory is empty — would make that unnecessary.

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
- Mounted at `/dagent` on the shared origin in `edge/nginx.conf` (prefix passed through, not
  stripped, plus the two patches in § 2), `basePath` compiled in via `DAGENT_BASE_PATH`, and
  `EMEHUB_AGENT_DAGENT_URL=/dagent` — so `GET /agents` reports registered and hand-off-ready and the
  Overview card's button is live.
- The Overview product card's `live` flag flipped from `false` to `true`: it read "Placeholder" for
  an application that is now deployed and reachable.
