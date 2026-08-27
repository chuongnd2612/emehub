"""Saved ticket queries — named clause queries, plus the shipped presets.

## Scoping: a person (or the workspace) **and** a project

Two axes, both nullable, and they answer different questions.

``owner_id`` is the hub's usual ownership column: a user's id, or NULL for the
shared namespace visible to everyone (ADR 0001 / `ownership.py`), exactly like
projects, tickets and knowledge.

``project_id`` is the *container* axis (#222). NULL means workspace-wide: the
query is offered in any project whose ``destination`` matches. A row that names a
project is offered in that project and nowhere else.

### This reverses what this docstring used to say

It argued the opposite, deliberately: "`dev-assistant` scoped its saved filters to
a *project*; here a query belongs to a person or to the workspace, which is the
axis everything else in this hub is already scoped on." The premise was true when
it was written and is no longer. Under project containment
([ADR 0011](../../../docs/adr/0011-project-containment-in-the-hub.md), which names
this module as the decision it reverses) the workspace is **not** the axis
ticket-shaped data is scoped on — the project is, and a saved *ticket* query is
ticket-shaped. A workspace-wide query applied inside a project either crosses the
project boundary, reintroducing the provider mismatch containment exists to make
impossible, or is silently narrowed to the current project — which is worse,
because the query then no longer means what its name says, while its
``description``, re-derived from the clauses on every write precisely so the two
cannot disagree, still describes the wider one.

Existing rows keep ``project_id IS NULL`` and stay workspace-wide; the migration
(`0017_saved_query_project`) reinterprets nothing. Only queries saved from inside a
project bind to one.

## Why `destination` is still a column

Unchanged by the above — it answers "which provider can run these clauses", not
"which project is this query about". A query is not portable across providers: one
naming ``areaPath`` cannot run on Jira at all, and ``parentId`` has no column in
the mirror. The capability matrix says so per destination, so a saved query has to
record which one it was built for. Without it the list would offer a query that is
guaranteed to be refused the moment it is applied.

## The unique constraint, and what it does *not* enforce

``(owner_id, project_id, destination, name)``. ``project_id`` is in it because
without it one project's "Backlog triage" would block the next project's, which is
the point of the scope.

Both engines treat NULLs as **distinct** in a unique index (Postgres by default —
``NULLS NOT DISTINCT`` is deliberately not used, so SQLite and Postgres behave
alike; SQLite has no other mode). So this constraint only bites when every column
is non-NULL, exactly as the three-column version did: it never policed the shared
namespace and it does not police workspace-wide rows now. The real check is
``services/saved_queries.create_query``, which compares NULLs with ``IS NULL`` and
therefore covers both. This is a backstop, not the rule.

## Built-ins

Shipped presets live in the same table as the user's own, told apart by
``built_in`` and ordered by ``position``. One list, one shape, and a built-in may
be used and **copied** but never edited or deleted — the route answers 409 and
says to duplicate it. That pattern is already argued through for `SavedPhrase` in
dev-assistant; a second shape for the same problem would be a second thing to keep
right. Built-ins are always workspace-wide (``project_id IS NULL``): a preset
belongs to a provider, never to one container.

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
        # A person may not have two queries of the same name for one destination
        # *within one project*; the shared namespace (owner_id NULL) and the
        # workspace-wide scope (project_id NULL) are each their own. Both engines
        # treat NULLs as distinct here, so those two cases are enforced in
        # `services/saved_queries`, not by this index — see the module docstring.
        UniqueConstraint(
            "owner_id", "project_id", "destination", "name", name="uq_saved_query_name"
        ),
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
    #: The container. NULL is workspace-wide — offered in every project on this
    #: `destination`. CASCADE rather than SET NULL: a query left behind by its
    #: project would be silently *widened* into projects whose area paths and
    #: iterations its clauses know nothing about, while its `description` still
    #: described the narrower query. See `0017_saved_query_project`.
    project_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=True, index=True
    )
    created_at: Mapped[datetime] = timestamp_column()
    updated_at: Mapped[datetime] = timestamp_column()
