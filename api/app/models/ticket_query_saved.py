"""Saved ticket queries — named clause queries, plus the shipped presets.

## Scoping follows the hub's own convention

``owner_id`` nullable, NULL meaning the shared namespace (ADR 0001 / `ownership.py`),
exactly like projects, tickets and knowledge. `dev-assistant` scoped its saved
filters to a *project*; here a query belongs to a person or to the workspace, which
is the axis everything else in this hub is already scoped on.

## Why `destination` is a column

A query is not portable across providers. One naming `areaPath` cannot run on Jira
at all, and `parentId` has no column in the mirror — the capability matrix says so
per destination, so a saved query has to record which one it was built for. Without
it the list would offer a query that is guaranteed to be refused the moment it is
applied.

## Built-ins

Shipped presets live in the same table as the user's own, told apart by
``built_in`` and ordered by ``position``. One list, one shape, and a built-in may be
used and **copied** but never edited or deleted — the route answers 409 and says to
duplicate it. That pattern is already argued through for `SavedPhrase` in
dev-assistant; a second shape for the same problem would be a second thing to keep
right.

``description`` is re-derived from the query on every write rather than stored as
typed, so it can never disagree with the clauses it describes.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, ForeignKey, Integer, JSON, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base, timestamp_column


class SavedTicketQuery(Base):
    __tablename__ = "saved_ticket_queries"
    __table_args__ = (
        # A person may not have two queries of the same name for one destination;
        # the shared namespace (owner_id NULL) is its own scope. Postgres treats
        # NULLs as distinct in a unique index, which is what allows one shared name
        # alongside each member's own.
        UniqueConstraint("owner_id", "destination", "name", name="uq_saved_query_name"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    #: `azure_devops` | `jira` | `github` | `mirror` — see the module docstring.
    destination: Mapped[str] = mapped_column(String(32), index=True)
    #: The `TicketQuery` verbatim: clauses, match, sort.
    query: Mapped[dict] = mapped_column(JSON, default=dict)
    #: Re-derived from `query` on every write, so the two cannot disagree.
    description: Mapped[str] = mapped_column(String(400), default="")
    #: A shipped preset: usable and copyable, never editable or deletable.
    built_in: Mapped[bool] = mapped_column(Boolean, default=False)
    #: Built-ins first, in this order; a user's own sort by name after them.
    position: Mapped[int] = mapped_column(Integer, default=0)

    owner_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True
    )
    created_at: Mapped[datetime] = timestamp_column()
    updated_at: Mapped[datetime] = timestamp_column()
