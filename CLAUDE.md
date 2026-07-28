# CLAUDE.md — EmeHub

Project-specific guidelines. Merge with the global `~/.claude/CLAUDE.md`.

**Read first:** [docs/CONTEXT.md](docs/CONTEXT.md) for vocabulary,
[docs/INTEGRATION.md](docs/INTEGRATION.md) for the contract with the agents, and
[docs/ROADMAP.md](docs/ROADMAP.md) for what phase we are in.

---

## What this repo is

EmeHub is the source of truth for identity and shared configuration across the EMESOFT agent
suite ([ADR 0001](docs/adr/0001-emehub-is-the-source-of-truth.md)). It does **not** do domain
work — no test generation, no code generation, no browsers, no Claude invocation for
end-user tasks. If a change adds domain behaviour to the hub, it belongs in an agent instead.

**Current state: Phase 0.** Documentation only. There is no `api/` or `app/` yet.

---

## Sibling repositories

The three repos are siblings on disk under `claude-projects/`:

| Path | App | Remote |
|---|---|---|
| `emehub/` | this repo | `chuongduong2810/emehub` |
| `q-agent/` | QAgent | `chuongduong2810/q-agent` |
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
design/             design system + landing mockup + brand assets
docs/               context, roadmap, integration contract, ADRs
```

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

## Design

Follow [design/DESIGN_SYSTEM.md](design/DESIGN_SYSTEM.md)
([ADR 0004](docs/adr/0004-inherit-the-q-agent-design-system.md)). Purple→indigo brand, cyan
highlight, semantic green/amber/rose — **no accent hues outside that set**. Satoshi for UI,
JetBrains Mono for ids/numbers/code. No emoji in UI. A new component is designed *in* this
language and the document is updated; the hub does not fork the system.

The visual design is being reworked and a new one will be supplied — check whether it has
landed before building significant UI.

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
