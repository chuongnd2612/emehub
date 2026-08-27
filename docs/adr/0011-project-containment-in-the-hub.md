# ADR 0011 — Project containment in the hub, and what we do not adopt from Q-Agent

- **Status:** Accepted
- **Date:** 2026-08-27
- **Amends:** the flat information architecture of the app shell — `NAV_GROUPS`
  (`app/src/components/shell/nav.ts:31-50`) and the route map (`app/src/router.tsx:77-86`).
  The URL-is-the-source-of-truth principle those two files were written around is unchanged
  and reinforced (CLAUDE.md › Frontend conventions).
- **Reverses:** the scoping argument in the module docstring of
  `api/app/models/ticket_query_saved.py:3-8` — saved ticket queries gain a project axis. See
  *Decisions on the handoff's open questions*, 1.
- **Source:** Q-Agent's [ADR 0015 — Project-scoped navigation and the run
  overlay](../../../q-agent/docs/adr/0015-project-scoped-navigation-and-run-overlay.md)
  (accepted 2026-08-26; epic `q-agent#726`, slices `#727`–`#734`, all merged), and the
  diagnosis that preceded it,
  [ADR 0013 — Project scoping model](../../../q-agent/docs/adr/0013-project-scoping-model.md).
  Transcribed for the hub in
  [docs/PROJECT-CONTAINMENT-HANDOFF.md](../PROJECT-CONTAINMENT-HANDOFF.md).
- **Epic:** [#223](https://github.com/chuongnd2612/emehub/issues/223) — **slices:**
  [#217](https://github.com/chuongnd2612/emehub/issues/217),
  [#218](https://github.com/chuongnd2612/emehub/issues/218),
  [#219](https://github.com/chuongnd2612/emehub/issues/219),
  [#220](https://github.com/chuongnd2612/emehub/issues/220),
  [#221](https://github.com/chuongnd2612/emehub/issues/221),
  [#222](https://github.com/chuongnd2612/emehub/issues/222)

## Context

Q-Agent has finished the refactor in which **the project is the container**: nothing ticket- or
run-shaped exists at its workspace level any more. The hub has the same flat information
architecture Q-Agent started from, and the same defect underneath it — scaled down, because
**the hub has no `Run` model.**

The defect is visible in the hub's own files.

**Three peers under one heading.** `app/src/components/shell/nav.ts:35-37` puts Overview,
Projects & Repositories and Tickets side by side in the `WORKSPACE` group. A ticket belongs to
a project and arrives through the connection configured on that project, so presenting Tickets
as a sibling of Projects is a claim about the domain that the domain does not make. A user
inside a project who clicks Tickets is thrown out of the project into an unfiltered,
workspace-wide list, with no way back to where they were.

**Flat routes mirror the flat nav.** `app/src/router.tsx:77-86` registers `projects`,
`projects/:projectId`, `tickets` and `tickets/:externalId` as flat siblings under `/app`. The
project tab is a query param instead — `?tab=`, read at
`app/src/screens/ProjectDetail/index.tsx:137-142`, options in
`app/src/screens/ProjectDetail/shared.ts:9-15`. That was the right shape while a tab was
intra-screen selection, and it is the wrong shape once a tab is a distinct view of a distinct
resource.

**A provider switch on a workspace-wide list.** `app/src/screens/Tickets/index.tsx:1-15`
records the design as "exactly one provider is active at a time, and the filter set changes
with it", selected by `?source=`. On a list that is not scoped to a project, that means the
same screen can show tickets from a provider which has nothing to do with the project the user
believes they are in. This is the argument that decided Q-Agent's ADR 0015 against a mere
filter, and it applies to the hub verbatim: a filter does not fix it, containment does.

**Referential integrity is missing at the one column all of this hangs on.**
`api/app/models/ticket.py:58` reads

```python
project_id: Mapped[int | None] = mapped_column(Integer, index=True, nullable=True)
```

— a nullable bare `Integer` with an index, not a foreign key. Nothing constrains it to an
existing project, and rows synced before project stamping hold `NULL`.

**But the capability is already there, and that is what makes this small.** The hub can
already answer "this project's tickets"; the Tickets screen simply never asks.

| Capability | Where | State |
| --- | --- | --- |
| Sync stamps the project | `api/app/services/ticket_service.py:541` | present |
| `GET /tickets` filters by project | `api/app/routers/tickets.py:357` — `projectId` | present |
| Per-project ticket counts | `api/app/services/project_service.py:160` | present |
| The web data layer accepts it | `app/src/data/tickets.ts:288`, `:297`, `:301` | present |

So this is a frontend information-architecture job with one small backend cleanup — not the
multi-slice backend migration Q-Agent needed, whose `Run` had no project column at all and
re-derived one by walking to the run's first ticket.

## Decision

**The project is the container for ticket-shaped data in the hub.** Four sections of Q-Agent's
ADR 0015 are adopted; the rest is explicitly not.

### Adopted — ADR 0015 §1, containment

Nothing ticket-shaped exists at workspace level. The sidebar becomes Overview, a **project
tree**, All projects, then the `PLATFORM` group unchanged; the standalone `Tickets` entry is
removed (#220). Each project row expands to its tabs, all rows collapsed on load, with a live
ticket count on the row.

`useSidebarStats()` already refuses to invent a number —
`app/src/components/shell/useSidebarStats.ts:27-31`: "`null` means 'not loaded yet or failed'
— the caller renders no badge rather than a stale or invented number." **Per-project counts
keep that property.** A count whose fetch fails renders no badge, never `0`.

Project detail gains a real **Tickets** tab, backed by `getTicketPage({ projectId })` (#221),
using the parameter the data layer already accepts. `PROJECT_TABS` becomes six entries, not
five.

### Adopted — ADR 0015 §2, routes nest under the project

```
/app/projects/:projectId/(overview|knowledge|repos|agents|tickets|settings)
/app/projects/:projectId/tickets/:externalId
```

Flat `/app/tickets` and `/app/tickets/:externalId` **redirect** to their nested equivalents so
existing links and bookmarks survive; a bare ticket link resolves its project from the ticket's
own `project_id`, and a ticket with none lands in the Unassigned bucket (#219). The project tab
becomes a **path segment**, retiring `?tab=`.

### Adopted — ADR 0015 §3, provider is derived from the project

The ticket source is read from the project's configured connection — `project_config` already
binds it. **There is no provider switch anywhere in the ticket flow.** Filter facets follow the
source: sprint / area path / state / work item type for ADO; sprint / epic / status / type /
priority for Jira. `?source=` disappears from the tickets route and is accepted on the redirect
path only, long enough not to break saved links (#221).

One part of §3 does **not** transfer. Q-Agent's three connection *roles* — `TICKET SOURCE`,
`CODE & KNOWLEDGE`, `TEST CASE TARGET` — and the new `test_case_connection_id` column belong to
a test-case pipeline the hub does not have. What is adopted is the principle, that provider is
a property of the project, not the role table. Nor does the hub face §3's
`Ticket.provider_kind` question: that column stays exactly as it is, stamped at sync from the
resolved connection (`api/app/services/ticket_service.py:539`), which is already the write
source ADR 0015 argued for.

### Adopted — ADR 0015 §8, counts have a single source

The project's Tickets tab, the sidebar badge and the Overview comparison table all read the
**same** project-scoped query. No screen computes a count its own way. That is the property
`useSidebarStats()` exists for — `useSidebarStats.ts:1-5`, "so the sidebar can never disagree
with the page it links to" — and this work must not undo it.

### `PLATFORM` stays flat

Claude Settings, Authentication, User Management, Integrations and Settings
(`app/src/components/shell/nav.ts:42-48`) are **workspace-level** and correctly peers of
Projects. Leave the group exactly as it is. Containment applies to ticket-shaped data, not to
platform administration: a credential, a session and a workspace member are not owned by a
project and never will be. This is a genuine peer of Projects that Q-Agent does not have, and
it is not an oversight that it survives the refactor.

## Deliberately NOT adopted

**The hub has no `Run` model.** Most of ADR 0015 is about runs, and none of that part applies
here. Stated plainly so the next reader does not go looking for a run overlay that was never
meant to exist in this repo:

| ADR 0015 | Not adopted | Because |
| --- | --- | --- |
| §4 | The full-screen run overlay: five human stages (Review → Automation → Execution → Evidence → Publish), the two hidden automatic stages (`processing`, `sync`) with a spinner chip instead of a stepper entry, Back/Next gating, and the viewed stage tracked separately from `run.status` | there is no run to open, no stages to step through, and no `run.status` |
| §5 | Link / subset / dry-run options moving into a Create Run modal | there is no Create Run modal, and no `CreateLinkSync` screen to take the options from |
| §6 | Completion as a terminal `done` stage, with success and needs-attention variants and *Retry failed publish* | there is nothing to complete and nothing to publish |

Also not adopted: **Q-Agent slices 1, 4, 5 and 8** — `Run.project_guid` stamping and backfill,
the overlay, the completion stage, and the chrome deletion (`RunSidebar`, `RunContextHeader`,
the in-run `navConfig` branch, the per-stage `PipelineRail`). None of those artefacts exist in
this repo, so there is nothing to build and nothing to delete.

ADR 0015 §7 — ticket detail reached only from the project — is subsumed by §2 here: the nested
`tickets/:externalId` route *is* that guarantee, and the hub's ticket detail has no "create run
from this ticket" or "add to run" action to re-home.

The hub therefore adopts §1, §2, §3 and §8. **Nothing else.**

## Decisions on the handoff's open questions

The handoff left three questions open. All three are answered here.

### 1. Saved ticket queries gain a project scope, and are migrated (#222)

`api/app/models/ticket_query_saved.py` is `owner_id` + `destination` scoped today, with no
project axis at all; the unique constraint is `("owner_id", "destination", "name")` (`:48`).
Its module docstring (`:3-8`) argues *deliberately against* project scoping:

> "`dev-assistant` scoped its saved filters to a *project*; here a query belongs to a person or
> to the workspace, which is the axis everything else in this hub is already scoped on."

**This ADR reverses that written decision**, and it should be read as a reversal rather than an
oversight. The premise was that the workspace is the axis everything else is scoped on. Under
containment that premise stops being true for ticket-shaped data — and a saved *ticket* query
is exactly that. A workspace-wide saved query applied inside a project would either cross the
project boundary, reintroducing the provider mismatch §3 exists to make impossible, or be
silently narrowed to the current project, which is worse: the query would no longer mean what
its name says, and its `description` — re-derived from the clauses on every write precisely so
the two cannot disagree — would still describe the wider query.

`destination` stays. It answers "which provider can run these clauses", which is a different
question from "which project is this query about", and the capability-matrix argument for it is
untouched.

### 2. The sidebar is a project tree, not a quick switcher (#220)

Matching ADR 0015 §1, which chose a tree with deliberately no quick switcher. Movement between
projects goes through the tree or the All-projects list. The hub shows one project today, so a
switcher would be optimising for a scale we have not met and cannot yet measure; the tree is
also the shape that gives a per-project count somewhere to live, which §8 needs. If real
workspaces turn out to hold dozens of projects, revisit — that is a sidebar change, not a
data-model one.

### 3. The Unassigned bucket is read-only for now (#217)

Backfill `project_id` from the ticket's `connection_id`, display whatever remains in an
explicit, counted **Unassigned** bucket, and **add no assign-to-project write.**

Tickets are billed throughout the hub as a *read-only mirror* of Azure DevOps and Jira
(`app/src/components/shell/nav.ts:71-74`), and the project a ticket belongs to is derived from
the connection it arrived through. A UI that let a user re-point one mirrored row at a
different project would be the first hub-side write to a mirror's own shape, and the next sync
would either overwrite it or have to learn to respect it. Neither is worth it to clear a
residue.

The migration must **log how many rows it could not backfill.** A migration that runs quietly
and leaves tickets invisible is the worst outcome available here.

## Consequences

**Good.** A project's Tickets tab becomes a real view of the project rather than a link out to
an unfiltered list. The provider mismatch becomes impossible by construction rather than merely
unlikely. `project_id` becomes a real FK, so the column the whole information architecture
hangs on can no longer point at a project that does not exist. And the hub skips the detour
Q-Agent took — deleting the project tabs (`q-agent#693`) and then reversing that once
containment made a real scoped list possible.

**One regression risk, and it is the reason for a hard gate.** Removing the standalone Tickets
entry removes **the only place in the hub where a workspace-wide question can be asked.** That
is a genuine loss, not a simplification, until Overview answers it — hence the project
comparison table (#218): per project, ticket source, ticket count, knowledge confidence,
connected agents, last sync. **#218 is a hard gate on #220.** If #218 slips, stop; shipping the
nav change without it is a regression. Overview is already billed as the "command center for
every EMESOFT agent" (`app/src/components/shell/nav.ts:63-66`), so this is the screen the
question belongs on.

**Three slices contend for the same files.** #219, #220 and #221 all touch the app shell and
the tickets screens, so they are **sequential, never parallel** (CLAUDE.md › Issue-driven
delivery workflow). #217 is backend-only and independent; #222 is sequenced after #217 to keep
a single Alembic head.

**No public contract change.** [INTEGRATION.md](../INTEGRATION.md) already documents
`GET /tickets` as "paged and filterable by project, provider, connection, state, assignee,
sprint and free text", and nothing here alters a token claim, a config endpoint shape or a
degradation behaviour. Saved ticket queries are not part of the agent-facing contract at all,
and the nested routes are the hub SPA's own. The cross-repo rule in CLAUDE.md is therefore not
triggered by this epic. If a later slice does widen a response shape, that PR carries the
INTEGRATION.md update and the two sibling issues — not this one.

**Unassigned is visible but inert.** Decision 3 means a user can see tickets that belong to no
project and can do nothing about them from the UI. That is a deliberate and temporary shape;
the escape hatch is a re-sync once the connection is bound to a project, not a hub-side write.

**`?tab=` and `?source=` become dead URL vocabulary.** Both are honoured on the redirect path
for the sake of existing links, which means the redirect layer carries a small amount of
legacy-parameter code that has to be kept until we are willing to break bookmarks.

## Alternatives considered

**Flat routes with a `?projectId=` filter** — ADR 0013 decision 2, already reversed by ADR 0015
§2. Rejected here for the same reason: a filter on a workspace-wide list does not prevent the
provider mismatch, because the list still *has* a provider switch of its own and a filter is a
suggestion the URL can drop. Containment removes the state that can disagree.

**Keep the standalone Tickets screen alongside the nested one.** Rejected: two ways to reach
the same rows, one of them unscoped, is the defect with a second route added. It also
guarantees the two count their totals differently, which is exactly what §8 forbids.

**A project switcher in the header instead of a tree.** Rejected — see decision 2. It is the
shape ADR 0015 explicitly declined, and it leaves nowhere to hang a per-project count.

**Resolve `NULL` `project_id` from `connection_id` alone, with no bucket.** Rejected: the
backfill leaves a residue, and the residue is precisely what silently vanishes under
containment. ADR 0015's own *Consequences* names this as the trap.
