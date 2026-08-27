# Handoff — project containment in the hub

Q-Agent has finished the v2 refactor in which **the project is the container**: nothing
ticket- or run-shaped exists at workspace level any more. The hub has the same flat
information architecture Q-Agent started from, and the same defect underneath it, so it
needs the same correction — scaled down, because the hub has no runs.

- Q-Agent's decision record: `../q-agent/docs/adr/0015-project-scoped-navigation-and-run-overlay.md`
  (accepted; epic `q-agent#726`, slices #727–#734, all merged).
- The diagnosis that preceded it: `../q-agent/docs/adr/0013-project-scoping-model.md`.

Read §5 before estimating: **most of ADR 0015 does not apply here.**

---

## 0. What is already true in the hub

Check this first, because it is better than it looks and it changes the size of the job.
The backend is essentially done:

| Capability | Where | State |
| --- | --- | --- |
| Project has a stable external identity | `api/app/models/project.py` — `guid`, unique globally | present |
| Tickets carry a project | `api/app/models/ticket.py:58` — `project_id` | nullable **bare `Integer`, not an FK** |
| Sync stamps the project | `api/app/services/ticket_service.py:541` | present |
| Tickets can be filtered by project | `api/app/routers/tickets.py:357` — `projectId` query param | present |
| Per-project ticket counts | `api/app/services/project_service.py:160` | present |
| The web data layer accepts it | `app/src/data/tickets.ts:288,297,301` — `projectId` | present |

So the hub already *can* answer "this project's tickets". **The Tickets screen simply never
asks.** This is a frontend information-architecture job with one small backend cleanup, not
the multi-slice backend migration Q-Agent needed — its `Run` had no project column at all
and had to derive one by walking to the run's first ticket.

---

## 1. Project is the container

### What is wrong today

`app/src/components/shell/nav.ts` puts three peers under `WORKSPACE`:

```
/app            Overview
/app/projects   Projects & Repositories
/app/tickets    Tickets                    <- belongs to a project, presented as a sibling
```

and `app/src/router.tsx` mirrors it: `/app/tickets` and `/app/tickets/:externalId` are flat
siblings of `/app/projects`. A user inside a project who clicks Tickets is thrown out of the
project into an unfiltered, workspace-wide list, with no way back to where they were.
Q-Agent closed this exact issue (#693) by *deleting* its project tabs, then had to reverse
that once containment made a real project-scoped list possible. Skip the detour.

### Wanted

- **Sidebar:** Overview, a **project tree**, All projects, then the `PLATFORM` group
  unchanged. The standalone `Tickets` entry is removed.
- Each project row expands to its tabs, all rows collapsed on load, with a live ticket count
  on the row. `useSidebarStats()` already computes real counts and already refuses to invent
  a number when a fetch fails — **keep that property**: a per-project count that fails
  renders no badge, never `0`.
- **Routes nest:**

```
/app/projects/:projectId/(overview|knowledge|repository|agents|tickets|settings)
/app/projects/:projectId/tickets/:externalId
```

  Flat `/app/tickets` and `/app/tickets/:externalId` **redirect** to their nested equivalents
  so existing links and bookmarks survive. Resolve the project for a bare ticket link from
  the ticket's own `project_id`; a ticket with none goes to the Unassigned bucket (§4).

- The project tab becomes a **path segment**, retiring `?tab=`. This is consistent with the
  hub's own rule (`router.tsx` header comment; CLAUDE.md › Frontend conventions): the URL is
  the source of truth. `?tab=` was right while a tab was intra-screen selection; once a tab
  is a distinct view of a distinct resource, it is a path.

### The cross-project view must not be lost

This is the one thing Q-Agent flagged as a **regression risk** rather than a simplification.
Removing the global ticket list takes away the only place a workspace-wide question can be
asked. In the hub that question belongs on **Overview**, which is already billed as the
"command center for every EMESOFT agent" — give it a project comparison table (per project:
ticket source, ticket count, knowledge confidence, connected agents, last sync) **before or
in the same slice as** the nav change.

Do not ship the removal without it.

---

## 2. Provider is derived from the project, not switched in the list

`app/src/screens/Tickets/index.tsx` carries its own provider switcher: `?source=` selects
`ado` or `jira`, and per its header comment "one provider is active at a time, and the
filter set changes with it".

This is the argument that decided Q-Agent's ADR 0015 against a mere filter, and it applies
verbatim here. A provider switch on a workspace-wide list means the same screen can show
tickets from a provider that has nothing to do with the project the user believes they are
in. **A filter does not fix that; containment does.** Provider is a property of the project —
`project_config` already binds the connection.

Wanted:

- The ticket source is read from the project's configured connection. **No provider switch
  anywhere in the ticket flow.**
- Filter facets follow the source: sprint / area path / state / work item type for ADO;
  sprint / epic / status / type / priority for Jira.
- `?source=` disappears from the tickets route. Keep accepting it on the redirect path only,
  long enough not to break saved links.
- **Check `ticket_query_saved` before you start.** Saved queries are likely provider-scoped
  today; under containment they become project-scoped. Decide whether to migrate them or
  scope them per project going forward, and say which in the PR.

---

## 3. Project detail gains a Tickets tab

`app/src/screens/ProjectDetail/` has Overview, Project knowledge, Repository, Agents,
Settings. Add **Tickets**, and make it a real view — `getTicketPage({ projectId })`, using the
parameter the data layer already accepts.

Its count, the sidebar badge and the Overview table must all read the **same** project-scoped
query. No screen may compute a count its own way; that is how a sidebar starts disagreeing
with the page it links to, which is precisely what `useSidebarStats()` was written to
prevent. Do not undo that.

---

## 4. `Ticket.project_id` — a real foreign key, plus an Unassigned bucket

Two separate problems, and the second is the dangerous one.

**Referential integrity.** `project_id` is a nullable bare `Integer` with an index — nothing
constrains it to an existing project. Promote it to a real FK to `projects.id`. Alembic
migration required (CLAUDE.md › Gates).

**Tickets that belong to no project.** Rows synced before project stamping have
`project_id = NULL`. Under containment they belong to no project and therefore **appear
nowhere** — not a display bug, a silent disappearance of data. Do this, in order:

1. **Backfill** `project_id` from the ticket's `connection_id`, since the connection is
   already bound to a project. This resolves most rows.
2. Whatever remains goes into an explicit, visible **"Unassigned" bucket** with its own
   count — never hidden, never guessed at.
3. The migration must **log how many rows it could not backfill.** A migration that runs
   quietly and leaves tickets invisible is the worst outcome available here.

Do not choose "resolve via `connection_id`" alone: it still leaves a residue, and the residue
is exactly what vanishes.

---

## 5. What NOT to copy from Q-Agent

ADR 0015 is mostly about runs. **The hub has no `Run` model.** Skip entirely:

- §4 — the full-screen run overlay, the five-stage stepper, the hidden automatic stages
- §5 — link options moving into a Create Run modal
- §6 — the terminal completion stage
- Q-Agent slices 1, 4, 5 and 8 (`Run.project_guid`, overlay, completion stage, chrome deletion)

What carries over is §1 (containment), §2 (nested routes), §3 (provider derived from the
project) and §8 (counts from a single source). Nothing else.

The hub also keeps a genuine peer of Projects that Q-Agent does not have: the entire
`PLATFORM` group — Claude Settings, Authentication, User Management, Integrations, Settings —
is workspace-level and correctly flat. **Leave it exactly as it is.** Containment applies to
ticket-shaped data, not to platform administration.

---

## 6. Slices

| # | Slice | Depends on |
| --- | --- | --- |
| 1 | `Ticket.project_id` → FK, backfill from `connection_id`, Unassigned bucket, migration logging | — |
| 2 | Overview project comparison table — the cross-project view that must exist *before* the removal | 1 |
| 3 | Nested project routes + redirects from `/app/tickets*`; the tab becomes a path segment | 1 |
| 4 | Sidebar project tree with live counts; remove the standalone Tickets entry | 2, 3 |
| 5 | Project → Tickets tab scoped by `projectId`; provider derived from the project; `?source=` and the switcher removed | 3 |

Slices 3, 4 and 5 all touch the shell and the tickets screens, so they are **sequential,
never parallel**. Slice 1 is backend-only and independent. Slice 2 is the guard on slice 4 —
if it slips, stop, because shipping 4 without it is a regression rather than a simplification.

Record the decision as an ADR in `docs/adr/`. **Check the directory before numbering** —
`0010` is currently used twice (`0010-a-provider-secret-may-cross-to-an-agent.md` and
`0010-one-origin-for-the-suite.md`). Reference Q-Agent's ADR 0015 as the source and state
plainly which parts were deliberately not adopted, so the next reader does not go looking for
a run overlay that was never meant to exist here.

---

## 7. Gates and verification

From `CLAUDE.md`:

- **`api/`** — `uv run pytest`, the app must boot, and an Alembic migration accompanies every
  schema change (slice 1 has one).
- **`app/`** — `npm run typecheck` (`tsc -b --noEmit`) + `npm run build`. There is **no unit
  test harness**; do not run `npm test`. Verify UI at runtime with `npm run dev` + Playwright.
- Branch `feature/<issue>` off `master`; PR → `gh pr merge <n> --squash --admin --delete-branch`.

Verification that actually proves something, rather than a green-looking run:

- **A ticket list must never be unscoped.** Assert on the requests: every `GET /tickets` the
  app issues from a project route carries `projectId`. Capture requests for the whole session
  and assert at the end — a revisited screen can serve from cache and issue nothing at all,
  so "no failures" is not the same as "it was checked".
- **Seed two projects on different providers.** With one project you cannot tell scoping from
  luck; "the other project's rows must not appear" is only a real assertion when there *is*
  another project. Q-Agent's fixture for exactly this is
  `../q-agent/api/scripts/probe_setup_732.py` — worth reading before writing the hub's.
- **Count the unassigned.** After the slice-1 migration, assert that the number of rows with
  `project_id IS NULL` equals the number the Unassigned bucket displays. If those disagree,
  tickets are hidden somewhere.

---

## Open questions for whoever picks this up

1. **Saved ticket queries** (`ticket_query_saved`) — migrate to project scope, or leave them
   workspace-wide and allow them to cross projects? §2 flags it; the call is not made here.
2. **A project tree, or a project switcher?** Q-Agent chose a tree with deliberately no quick
   switcher. The hub shows one project today; if real workspaces hold dozens, listing them
   all in the sidebar may be the wrong shape, and a switcher plus the All-projects list may
   be better. Decide before slice 4.
3. **Does the Unassigned bucket need write access** — can a user assign such a ticket to a
   project from the UI, or is backfill-only sufficient for now?
