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
    project_id: Mapped[int | None] = mapped_column(Integer, index=True, nullable=True)
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
