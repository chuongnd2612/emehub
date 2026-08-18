# CLAUDE.md — EmeHub

Project-specific guidelines. Merge with the global `~/.claude/CLAUDE.md`.

**Read first:** [docs/CONTEXT.md](docs/CONTEXT.md) for vocabulary,
[docs/INTEGRATION.md](docs/INTEGRATION.md) for the contract with the agents, and
[docs/ROADMAP.md](docs/ROADMAP.md) for what phase we are in.

---

## What this repo is

EmeHub is the source of truth for identity and shared configuration across the EMESOFT agent
suite ([ADR 0001](docs/adr/0001-emehub-is-the-source-of-truth.md)).

**The boundary:** the hub *builds the shared artefacts it already owns every input for* —
which today means knowledge bases, and nothing else
([ADR 0007](docs/adr/0007-knowledge-builds-run-on-the-hub.md)). It does **not** do an agent's
job: no test generation, no code generation, no browser automation, no PR creation. If a
change adds domain behaviour beyond that carve-out, it belongs in an agent instead.

**Current state.** The hub is built and running: FastAPI + Postgres behind nginx, all eleven
UI views live against real endpoints, ~408 backend tests. What has *not* happened is the
agent cutover — neither Q-Agent nor D-Agent consumes the hub yet, so it runs in parallel with
both rather than in front of them. See [docs/ROADMAP.md](docs/ROADMAP.md).

---

## Sibling repositories

The three repos are siblings on disk under `claude-projects/`:

| Path | App | Remote |
|---|---|---|
| `emehub/` | this repo | `chuongnd2612/emehub` |
| `q-agent/` | QAgent | `chuongnd2612/q-agent` |
| `ticket-executor/` | DAgent (to be renamed `d-agent`) | `DaoLinh98/ticket-executor` |

Read the other two freely — they are the source material for most of this repo's decisions.
**Never modify them from a hub task.** A change needed in QAgent or DAgent is an issue in
*that* repo.

Note the app in `ticket-executor/` is one level down: `ticket-executor/ticket-executor/`.

---

## Stack & layout *(target — Phase 1)*

```
api/                FastAPI (Python 3.13, uv), SQLAlchemy 2, Alembic, Postgres 16
app/                React 19, Vite, TypeScript, Tailwind 4
docker-compose.yml  api + db + web (nginx)
edge/               the suite's front door — one origin for hub + agents (own compose project)
dagent/             D-Agent's container, built from the sibling checkout (own compose project)
design/             design system + landing mockup + brand assets
docs/               context, roadmap, integration contract, ADRs
```

`dagent/` deploys an application that lives in another repository, which is the one place this repo
builds something it does not own. It is a stopgap with a written exit
([docs/DAGENT-HANDOFF.md §1](docs/DAGENT-HANDOFF.md)) and not a licence to keep sibling code here —
D-Agent ships no container assets of its own, and the alternative was leaving it the one app in the
suite that is not deployed.

Mirrors QAgent deliberately ([ADR 0002](docs/adr/0002-stack-fastapi-react-mirroring-q-agent.md)).
Config is prefixed `EMEHUB_`; ports must not clash with QAgent's (api 8787, web 5174, db 5456)
so both stacks can run on one host during migration.

## Build & verify *(once code exists)*

- **`api/`** — `uv run pytest` and the app must boot. Alembic migration for every schema change.
- **`app/`** — `npm run typecheck` (`tsc -b --noEmit`) + `npm run build`. There is **no unit-test
  harness**; do not run `npm test`. Verify UI at runtime with `npm run dev` + Playwright.
- **Docker** — after anything ships, rebuild: `docker compose up -d --build`. The running
  container is stale until you do. Say so explicitly in your response.

---

## Security rules (non-negotiable)

These exist because the hub holds every credential in the suite.

- **Two secrets, never one.** `EMEHUB_JWT_SECRET` signs tokens; `EMEHUB_ENCRYPTION_KEY`
  encrypts data at rest. Never derive one from the other, never reuse one for the other.
  ([ADR 0005](docs/adr/0005-secret-and-key-management.md))
- **No boot-time secret generation.** Missing secret → refuse to start. A generated fallback
  encryption key silently creates rows that cannot be decrypted after the next restart.
- **Never fail open.** There is no configuration in which authentication being unavailable
  results in access being granted. If you find yourself writing an `authDisabled()`, stop —
  that is the exact bug being removed from DAgent
  ([INTEGRATION.md §6.1](docs/INTEGRATION.md#61-dagents-auth-gate-disables-itself)).
- **Provider PATs never leave the hub.** The hub proxies provider calls. The Claude credential
  is the one documented exception, because the CLI needs it on disk
  ([INTEGRATION.md §4](docs/INTEGRATION.md#4-secrets-that-cross-the-boundary)).
- **Never log or return a secret.** Endpoints return `hasPat: true`, never the PAT.
- **Secrets stay out of git.** Only `.env.example` is tracked.

---

## Frontend conventions

Carried over from QAgent, each one learned the hard way:

- Render floating overlays (dropdowns, popovers, tooltips, menus) via a portal to
  `document.body` with fixed positioning anchored to the trigger's bounding rect. Ancestor
  `backdrop-filter` / `transform` / `filter` create stacking contexts that trap child
  `z-index`.
- Don't use `backdrop-filter` on panels layered over animated content — use an opaque
  background. Animated backdrops cause compositing artifacts and the filter itself is a
  stacking-context trap.
- When portalling a Framer Motion element, call `createPortal` on the outside and let
  `AnimatePresence` directly wrap the `motion` element inside — `AnimatePresence` must be the
  direct parent of the animating child or it won't mount/animate.
- **The URL is the source of truth for navigation**, not the store. Zustand holds UI-only
  state (modals, filters, drafts). Intra-screen selection goes in query params.
- For visual layering/rendering bugs, inspect the live DOM (`elementFromPoint`, computed
  styles) to find the actual cause **before** fixing. Don't iterate on opacity/z-index guesses.

## Design — the handoff is binding

The design lives in **[design/design_handoff_emehub/](design/design_handoff_emehub/)** and it
is the source of truth for every pixel. Read in this order:

1. **`README.md`** — the spec: screens, components, tokens, motion, state. Binding.
2. **`EmeHub.dc.html`** — the working prototype. A **design reference, not code to copy**.
   Open it in a browser when motion or a detail is ambiguous.
3. **`Q-Agent-DESIGN_SYSTEM.md`** — the system it extends (foundations, voice).
4. **`Q-Agent.ref.html`** — the sibling product, for ambiguous credential / connection /
   ticket-filter behaviour.

`support.js` is the prototype's rendering harness. **Never port it, never read it for
patterns.**

([ADR 0006](docs/adr/0006-implementing-the-emehub-design-handoff.md);
[ADR 0004](docs/adr/0004-inherit-the-q-agent-design-system.md) is superseded.)

### Rules

- **Tokens are CSS custom properties, named exactly as the handoff names them**
  (`--bg`, `--panel`, `--card`/`--card2`/`--card3`, `--bd`/`--bd2`/`--bd3`, `--pop`, `--txt`…
  `--txt4`, `--muted`, `--faint`, `--label`, `--p`/`--pl`/`--ps`/`--pg`/`--pglow`/`--pt`/`--pb`,
  `--pOn`, `--psText`, `--silver`, `--terra`). Light mode and accent switching depend on those
  exact names — do not rename them to Tailwind-idiomatic ones.
- **Never write a raw colour in a component.** Always a token. A hex in a `.tsx` file is a bug.
- **Four accents, and the default is EMESOFT Red `#e1172b`** — not purple. The others are
  Agent Purple, Signal Cyan, Metallic Steel. Accent is a user setting on the app root.
- **Light mode is mandatory**, not an afterthought. Every pale hue used as *foreground text*
  needs its darkened counterpart from the handoff's darkening map
  (`#6ee7b7→#0b6d4c`, `#fbbf24→#8a5b00`, `#fb7185→#a5123c`, `#67e8f9→#0d6a7a`,
  `#a78bfa→#5b3fc4`, …), and pill tint alpha goes to `.15`. Nothing below 4.5:1.
- **No inline styles.** The prototype's `style="…"` is a constraint of the tool that produced
  it — the handoff explicitly says to use our own conventions. Tailwind utilities bound to the
  token layer. (This reverses the Q-Agent system's inline-style rule.)
- **Restore the two transitions the prototype dropped**: toggle knob
  `left .22s cubic-bezier(.2,.7,.3,1)`, and `background/border-color/color .2s` on
  theme-token-driven surfaces. The prototype removed them for tool reasons only.
- **Motion is specified, not improvised.** Keyframes, pointer-tilt maths and async feedback
  timings come from the handoff's Motion tables verbatim. Pointer tilt is gated by the
  *Depth on hover* setting; particle count drops under `prefers-reduced-motion`.
- **Icons** are inline SVG, Feather/Lucide style: `viewBox="0 0 24 24"`, `fill="none"`,
  `stroke="currentColor"`, `stroke-width:2–2.6`, round caps/joins, 12–22 px. Reach for
  `lucide-react` only where the glyph matches exactly. The Claude mark is a filled 5-point
  star in `#D97757`. No icon fonts, no raster icons, no illustrations, **no emoji**.
- **Fonts self-hosted** — Satoshi (400/500/700/900) and JetBrains Mono (400/500/600). No CDN.
- **Desktop-first, canvas 1512×950**, sidebar fixed 268 px. **Mobile layouts are not
  designed — ask before inventing them.** Known degradations if you must go narrower: the
  header title truncates first, tables scroll horizontally below ~1100 px, 3-up grids collapse
  3→2→1, sidebar becomes an overlay drawer under ~1024 px.
- **The header title must be the flexible item and must truncate**, or it overlaps the search
  field at narrow widths. This is called out in the spec because it is easy to get wrong.
- **Where an endpoint does not exist, stub it behind the typed data layer** (`app/src/data/`)
  shaped like the handoff's *Data fetching* section — and say so in your response. Never
  invent an API route silently.
- **Copy is final.** Labels, placeholders, empty states and toast text are as written in the
  handoff. Do not paraphrase.

### Voice

Confident, concise, product-led. Sentence case in UI; UPPERCASE only for small tracked labels.
Empty states get a glyph, a one-line explanation and a primary CTA — never a bare "no data".

---

## Issue-driven delivery workflow

Default for every feature, enhancement or bug. Standing directive — don't ask permission for
the process itself.

1. **Clarify first** if the request is ambiguous.
2. **Open a GitHub issue** (`gh issue create` — no `--json` here; capture the number from the
   returned URL; multi-line bodies via `--body-file`, not nested heredocs).
3. **Slice vertically** into independently-shippable issues. File-disjoint slices run in
   parallel via `general-purpose` sub-agents; slices sharing a core file are sequenced.
4. **Branch per issue** off `master`: `feature/<n>`, `bug/<n>`, `docs/<n>`.
5. **Implement + verify** against the gates above.
6. **PR → self-merge**: `gh pr merge <n> --squash --admin --delete-branch`. Auto-merging
   self-authored PRs is pre-authorized for this project.
7. **Rebuild Docker** after shipping, and confirm it in your response.

Default branch is **`master`**. "Merge to main" means merge to `master`.

### Cross-repo rule

Any change to the hub's **public contract** — token claims, config endpoint shapes,
degradation behaviour — requires:

1. an update to [docs/INTEGRATION.md](docs/INTEGRATION.md) in the same PR, and
2. a matching issue opened in **both** `q-agent` and `ticket-executor` before merge.

The contract document is the interface. Changing it silently breaks two other applications.

> **Open item:** the three repos sit under two GitHub accounts, so cross-repo issue creation
> may need credentials you don't have. Say so rather than skipping step 2.

---

## Tooling

- In the Bash tool, use bash heredocs for multi-line commit messages; never PowerShell
  here-string syntax (`@'...'@`) — it leaks literal characters into the message.
