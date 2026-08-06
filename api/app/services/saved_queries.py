"""Saved ticket queries: the shipped presets, and CRUD over the user's own.

## The presets

Ported in spirit from `dev-assistant/packages/shared/src/presets.ts`, including the
detail that matters most: **state clauses list cross-template spellings.** Azure
DevOps process templates disagree — Agile says `Active`, Scrum says `Committed`,
Basic says `Doing` — so a preset naming one of them works in one project and
silently returns nothing in the next. `in` with all of them is the only version
that travels.

They are seeded idempotently on every read rather than in the migration, so a
preset can be corrected in code without a data migration chasing it. Keyed by
`(destination, name)` in the shared namespace.

## Why the ADO and mirror presets differ

`@Me` is a real macro at Azure DevOps and it resolves there. Against our own
columns it can only be matched as the viewer's *display* name, which depends on the
provider spelling people the same way the hub does — so the mirror's presets stay
off assignee and lean on the fields it holds cleanly.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Query, Session

from app.db import utcnow
from app.models.ticket_query_saved import SavedTicketQuery
from app.models.user import User
from app.services import ticket_query
from app.services.ownership import owned

#: Spellings of the same state across ADO's process templates. A preset naming one
#: works in one project and returns nothing in the next, so they are listed.
ACTIVE_STATES = ["Active", "In Progress", "Committed", "Doing"]
REVIEW_STATES = ["Code Review", "Resolved", "In Review", "Ready for QA"]
DONE_STATES = ["Closed", "Done", "Completed"]


def _q(clauses: list[dict[str, Any]], match: str = "all", sort: str = "changedDate") -> dict:
    return {
        "clauses": clauses,
        "match": match,
        "sort": {"field": sort, "direction": "desc"},
    }


def _clause(field: str, operator: str, values: list[str]) -> dict[str, Any]:
    return {"field": field, "operator": operator, "values": values}


#: `(destination, name, query)`, in the order they are offered.
PRESETS: tuple[tuple[str, str, dict], ...] = (
    (
        "azure_devops",
        "Mine · active now",
        _q([_clause("assignee", "is", ["@Me"]), _clause("state", "in", ACTIVE_STATES)]),
    ),
    (
        "azure_devops",
        "Mine · current sprint",
        _q(
            [
                _clause("assignee", "is", ["@Me"]),
                _clause("iterationPath", "under", ["@CurrentIteration"]),
            ]
        ),
    ),
    (
        "azure_devops",
        "Mine · in review",
        _q([_clause("assignee", "is", ["@Me"]), _clause("state", "in", REVIEW_STATES)]),
    ),
    (
        "azure_devops",
        "Changed since yesterday",
        _q([_clause("changedSince", "onOrAfter", ["@Today - 1"])]),
    ),
    (
        "azure_devops",
        "Open bugs",
        _q(
            [
                _clause("workItemType", "is", ["Bug"]),
                _clause("state", "notIn", DONE_STATES),
            ]
        ),
    ),
    # The mirror's own. No assignee: `@Me` can only be matched here as a display
    # name, which depends on the provider spelling people as the hub does.
    (
        "mirror",
        "Open bugs",
        _q(
            [
                _clause("workItemType", "is", ["Bug"]),
                _clause("state", "notIn", DONE_STATES),
            ]
        ),
    ),
    (
        "mirror",
        "Active work",
        _q([_clause("state", "in", ACTIVE_STATES)]),
    ),
    (
        "mirror",
        "Changed in the last week",
        _q([_clause("changedSince", "onOrAfter", ["@Today - 7"])]),
    ),
)


class BuiltInIsReadOnly(RuntimeError):
    """A shipped preset may be used and copied, never edited or deleted."""


class DuplicateName(ValueError):
    """This scope already has a query by that name."""


def _visible(db: Session, user: User | None) -> Query[SavedTicketQuery]:
    return owned(db.query(SavedTicketQuery), SavedTicketQuery, user)


def _describe(query: dict) -> str:
    """The stored description, re-derived so it cannot disagree with the clauses."""
    return ticket_query.describe(ticket_query.query_from_wire(query))[:400]


def seed_built_ins(db: Session) -> int:
    """Ensure every shipped preset exists in the shared namespace. Idempotent.

    Keyed on `(destination, name)`, so correcting a preset's clauses in code
    updates the row on the next read rather than needing a data migration.
    """
    written = 0
    for position, (destination, name, query) in enumerate(PRESETS):
        row = (
            db.query(SavedTicketQuery)
            .filter(
                SavedTicketQuery.owner_id.is_(None),
                SavedTicketQuery.destination == destination,
                SavedTicketQuery.name == name,
            )
            .one_or_none()
        )
        if row is None:
            db.add(
                SavedTicketQuery(
                    name=name,
                    destination=destination,
                    query=query,
                    description=_describe(query),
                    built_in=True,
                    position=position,
                    owner_id=None,
                )
            )
            written += 1
        elif row.query != query or row.position != position:
            row.query = query
            row.description = _describe(query)
            row.position = position
            row.built_in = True
            db.add(row)
            written += 1
    if written:
        db.commit()
    return written


def list_queries(
    db: Session, user: User | None, *, destination: str | None = None
) -> list[SavedTicketQuery]:
    """Presets first in their own order, then the caller's own by name."""
    seed_built_ins(db)
    query = _visible(db, user)
    if destination:
        query = query.filter(SavedTicketQuery.destination == destination)
    return query.order_by(
        SavedTicketQuery.built_in.desc(),
        SavedTicketQuery.position,
        SavedTicketQuery.name,
    ).all()


def get_query(db: Session, user: User | None, query_id: int) -> SavedTicketQuery | None:
    """One row, or None. A row owned by someone else is indistinguishable from a
    row that does not exist — the caller turns None into a 404, never a 403."""
    return _visible(db, user).filter(SavedTicketQuery.id == query_id).one_or_none()


def create_query(
    db: Session,
    user: User | None,
    *,
    name: str,
    destination: str,
    query: dict,
    shared: bool = False,
) -> SavedTicketQuery:
    owner_id = None if shared else (user.id if user else None)
    clash = (
        db.query(SavedTicketQuery)
        .filter(
            SavedTicketQuery.owner_id.is_(None) if owner_id is None else SavedTicketQuery.owner_id == owner_id,
            SavedTicketQuery.destination == destination,
            SavedTicketQuery.name == name,
        )
        .one_or_none()
    )
    if clash is not None:
        raise DuplicateName(f"“{name}” is already saved here.")

    row = SavedTicketQuery(
        name=name,
        destination=destination,
        query=query,
        description=_describe(query),
        built_in=False,
        position=0,
        owner_id=owner_id,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def update_query(
    db: Session,
    row: SavedTicketQuery,
    *,
    name: str | None = None,
    query: dict | None = None,
) -> SavedTicketQuery:
    if row.built_in:
        raise BuiltInIsReadOnly("A shipped query cannot be edited. Duplicate it and edit the copy.")
    if name is not None:
        row.name = name
    if query is not None:
        row.query = query
        row.description = _describe(query)
    row.updated_at = utcnow()
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def delete_query(db: Session, row: SavedTicketQuery) -> None:
    if row.built_in:
        raise BuiltInIsReadOnly("A shipped query cannot be deleted. Duplicate it and edit the copy.")
    db.delete(row)
    db.commit()


def duplicate_query(
    db: Session, user: User | None, row: SavedTicketQuery, *, name: str | None = None
) -> SavedTicketQuery:
    """A copy the caller owns — **always** editable, even from a built-in.

    This is what makes read-only presets tolerable rather than a dead end: the
    answer to "I want this but slightly different" is one click.
    """
    wanted = name or f"{row.name} copy"
    # Nudge past an existing copy rather than refusing, since duplicating twice is
    # a normal thing to do.
    suffix = 2
    while (
        db.query(SavedTicketQuery)
        .filter(
            SavedTicketQuery.owner_id == (user.id if user else None),
            SavedTicketQuery.destination == row.destination,
            SavedTicketQuery.name == wanted,
        )
        .one_or_none()
        is not None
    ):
        wanted = f"{name or row.name} copy {suffix}"
        suffix += 1

    return create_query(
        db,
        user,
        name=wanted,
        destination=row.destination,
        query=dict(row.query or {}),
    )
