"""Ticket model — a work item synced from a provider, ported from QAgent.

The hub is the **store**, not the source: rows here are a normalised mirror of
work items that live in Azure DevOps / Jira / GitHub. Agents read them through
``GET /tickets`` and ``GET /tickets/{external_id}`` (INTEGRATION.md §3) instead
of each agent discovering and re-normalising the same work items per run
(ROADMAP Phase 4).

Two deliberate differences from QAgent's table:

* **No ``note`` column.** QAgent's ``note`` is a QA-run annotation — domain work,
  which the hub does not do (CLAUDE.md › What this repo is). The hub stores only
  what the provider gave it.
* **``owner_id`` is the workspace scoping column** (nullable FK to ``users.id``;
  NULL means the workspace-wide shared namespace), the same convention every
  scoped table in the hub follows — see ``app.services.ownership``.

## ``project_id`` — a real foreign key, and why ``SET NULL``

``project_id`` is a declared ``ForeignKey("projects.id")`` (migration ``0016``).
Three ``ondelete`` behaviours were possible and only one of them is safe here:

* **CASCADE** silently destroys mirrored work items as a side effect of tidying
  the project registry. A ticket is the only hub-side record that a work item
  was ever synced, and a re-sync needs the connection that was bound to the
  project being deleted — so the destruction is not undoable from the hub.
* **RESTRICT** looks right, because ``project_service.delete_project`` already
  refuses (``ProjectHasTickets``) when tickets still point at the row. But
  ``projects.owner_id`` is ``ON DELETE CASCADE`` from ``users``, so deleting a
  member cascades their projects — and a database-level RESTRICT would abort
  that unrelated delete with an ``IntegrityError`` the caller cannot act on.
* **SET NULL** is what ships. The ordinary delete path is still refused at the
  service layer with a countable, actionable error, so SET NULL is only ever
  reached by a cascade. When it is, the rows land in the **Unassigned bucket** —
  which since this slice has an explicit selector (``GET /tickets?unassigned=true``)
  and a count of its own (``GET /projects/ticket-counts``), so they are visible
  rather than orphaned or gone.

``connection_id`` points at the work-item connection a ticket was synced from,
so downstream work routes back to the same origin. It is a **plain nullable
integer**, not a declared ``ForeignKey``, because the ``provider_connections``
table is owned by the connections slice and does not exist here yet: SQLAlchemy
resolves a foreign-key target the first time the mapper emits SQL, so declaring
``ForeignKey("provider_connections.id")`` now makes every ticket query raise
``NoReferencedTableError``. The column holds exactly the same values either way.
Once the connections slice has landed, the constraint is two lines — a
``ForeignKey("provider_connections.id")`` here and an ``op.create_foreign_key``
in a follow-up migration. This module still never imports that slice.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base, timestamp_column

#: Provider kinds the hub knows how to store tickets for. Not enforced by a
#: constraint — a provider the hub has not heard of should still round-trip.
PROVIDER_KINDS = ("ado", "jira", "github")

#: Common work-item statuses/priorities, for UI pills. Advisory, not a CHECK:
#: provider states are project-configurable and an unknown one must not 500.
STATUSES = ("Ready for QA", "In Progress", "Blocked", "Done")
PRIORITIES = ("High", "Medium", "Low")


class Ticket(Base):
    __tablename__ = "tickets"

    id: Mapped[int] = mapped_column(primary_key=True)
    #: The provider's own identifier, e.g. "SUR-1428". Unique per
    #: (provider_kind, owner) rather than globally — two users may each hold
    #: their own copy of the same work item.
    external_id: Mapped[str] = mapped_column(String(64), index=True)
    provider_kind: Mapped[str] = mapped_column(String(16), index=True)
    #: The project this work item belongs to. A real FK since 0016 — see the
    #: module docstring for why ``ondelete="SET NULL"`` and not RESTRICT/CASCADE.
    project_id: Mapped[int | None] = mapped_column(
        ForeignKey("projects.id", ondelete="SET NULL"), index=True, nullable=True
    )
    #: References ``provider_connections.id``. Unconstrained until that table
    #: exists — see the module docstring.
    connection_id: Mapped[int | None] = mapped_column(Integer, index=True, nullable=True)

    title: Mapped[str] = mapped_column(String(500), default="")
    work_item_type: Mapped[str] = mapped_column(String(32), default="User Story")
    status: Mapped[str] = mapped_column(String(32), default="Ready for QA")
    priority: Mapped[str] = mapped_column(String(16), default="Medium")
    assignee: Mapped[str] = mapped_column(String(120), default="")
    sprint: Mapped[str] = mapped_column(String(120), default="")
    area_path: Mapped[str] = mapped_column(String(300), default="")
    epic: Mapped[str] = mapped_column(String(300), default="")

    description: Mapped[str] = mapped_column(Text, default="")
    #: The work item's page in the provider — the ADO ``_workitems/edit`` link,
    #: the Jira ``/browse`` link, the GitHub issue's ``html_url``. Every adapter
    #: already normalises it; storing it is what lets a consumer send a human
    #: back to the source without holding a connection of its own. ``""`` when
    #: the connection had no org/base URL to build one from.
    url: Mapped[str] = mapped_column(String(1000), default="")

    labels: Mapped[list] = mapped_column(JSON, default=list)
    acceptance_criteria: Mapped[list] = mapped_column(JSON, default=list)  # list[str]
    # The provider's original AC as rich HTML, kept alongside the split list so a
    # consumer can render it read-only when the criteria don't split cleanly.
    acceptance_criteria_html: Mapped[str] = mapped_column(Text, default="")
    comments: Mapped[list] = mapped_column(JSON, default=list)
    attachments: Mapped[list] = mapped_column(JSON, default=list)
    linked_prs: Mapped[list] = mapped_column(JSON, default=list)

    synced_at: Mapped[datetime] = timestamp_column()
    # Workspace scoping: NULL == shared. See app.services.ownership.
    owner_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )

    @property
    def ac_count(self) -> int:
        return len(self.acceptance_criteria or [])
