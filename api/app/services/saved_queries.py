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
`(destination, name)` in the shared namespace, **with no project** — a preset
belongs to a provider, never to one container, so the key names
`project_id IS NULL` explicitly rather than relying on there being nothing else
to collide with.

## The project axis (#222)

`project_id` is NULL for workspace-wide and a project's id for one container.
`list_queries(project_id=…)` offers a project **its own rows plus the
workspace-wide ones**, and nothing belonging to another project. Omitting
`project_id` is the *management* view — everything the caller may see, so a
project-bound query can still be listed and deleted from outside its project, and
so an agent reading `GET /ticket-queries` sees what it always did.

**Where the name-clash rule really lives.** `uq_saved_query_name` covers
`(owner_id, project_id, destination, name)` but both engines treat NULLs as
distinct in a unique index, so it does not bite on shared (`owner_id IS NULL`) or
workspace-wide (`project_id IS NULL`) rows. `create_query` compares both columns
with `IS NULL` and is therefore the check that actually holds; the constraint is a
backstop for the fully-specified case.

## Why the ADO and mirror presets differ

`@Me` is a real macro at Azure DevOps and it resolves there. Against our own
columns it can only be matched as the viewer's *display* name, which depends on the
provider spelling people the same way the hub does — so the mirror's presets stay
off assignee and lean on the fields it holds cleanly.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import or_
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


def _in_scope(column, value: int | None):  # noqa: ANN001, ANN202
    """``column = value``, but matching NULL with ``IS NULL``.

    ``column == None`` renders as ``= NULL``, which is never true. Getting this
    wrong on either nullable axis silently stops the clash check from seeing the
    shared namespace or the workspace-wide scope at all, and the unique index
    cannot catch what it misses (both engines treat NULLs as distinct).
    """
    return column.is_(None) if value is None else column == value


def _describe(query: dict) -> str:
    """The stored description, re-derived so it cannot disagree with the clauses."""
    return ticket_query.describe(ticket_query.query_from_wire(query))[:400]


def seed_built_ins(db: Session) -> int:
    """Ensure every shipped preset exists in the shared namespace. Idempotent.

    Keyed on `(destination, name)` with `project_id IS NULL`, so correcting a
    preset's clauses in code updates the row on the next read rather than needing a
    data migration — and a *project-bound* shared query that happens to carry a
    preset's name is a different row, not a preset to be rewritten.
    """
    written = 0
    for position, (destination, name, query) in enumerate(PRESETS):
        row = (
            db.query(SavedTicketQuery)
            .filter(
                SavedTicketQuery.owner_id.is_(None),
                SavedTicketQuery.project_id.is_(None),
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
                    project_id=None,
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
    db: Session,
    user: User | None,
    *,
    destination: str | None = None,
    project_id: int | None = None,
) -> list[SavedTicketQuery]:
    """Presets first in their own order, then the caller's own by name.

    ``project_id`` narrows to what may be offered *inside* that project: its own
    rows plus the workspace-wide ones (``project_id IS NULL``, which includes every
    preset). Another project's rows are excluded — that exclusion is the whole
    point of the axis, and a stored column nothing filters on would not be one.

    Omitting it lists everything the caller may see, project-bound rows included:
    the management view, and what an agent reading this endpoint has always got.
    """
    seed_built_ins(db)
    query = _visible(db, user)
    if destination:
        query = query.filter(SavedTicketQuery.destination == destination)
    if project_id is not None:
        query = query.filter(
            or_(
                SavedTicketQuery.project_id.is_(None),
                SavedTicketQuery.project_id == project_id,
            )
        )
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
    project_id: int | None = None,
) -> SavedTicketQuery:
    """Save one query. ``project_id`` binds it to a project; None is workspace-wide.

    The clash check is per *scope*, and the scope is both nullable axes: the same
    name may exist once per (owner, project, destination). It has to be done here
    rather than left to `uq_saved_query_name`, because a unique index treats NULLs
    as distinct on both engines and so never sees the shared or workspace-wide
    cases. `.first()`, not `.one_or_none()`: a pre-existing duplicate the index
    could not have caught must still be reported as a clash, not raise.
    """
    owner_id = None if shared else (user.id if user else None)
    clash = (
        db.query(SavedTicketQuery)
        .filter(
            _in_scope(SavedTicketQuery.owner_id, owner_id),
            _in_scope(SavedTicketQuery.project_id, project_id),
            SavedTicketQuery.destination == destination,
            SavedTicketQuery.name == name,
        )
        .first()
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
        project_id=project_id,
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
    db: Session,
    user: User | None,
    row: SavedTicketQuery,
    *,
    name: str | None = None,
    project_id: int | None = None,
) -> SavedTicketQuery:
    """A copy the caller owns — **always** editable, even from a built-in.

    This is what makes read-only presets tolerable rather than a dead end: the
    answer to "I want this but slightly different" is one click.

    A duplicate is a save, so it lands in the scope it was made from:
    ``project_id`` when the caller was inside a project, otherwise the source's own
    scope. Copying a workspace-wide preset from inside a project is exactly how a
    project gets its first query, and the copy is the caller's own — a built-in is
    never rewritten.
    """
    target_project_id = project_id if project_id is not None else row.project_id
    wanted = name or f"{row.name} copy"
    # Nudge past an existing copy rather than refusing, since duplicating twice is
    # a normal thing to do.
    suffix = 2
    while (
        db.query(SavedTicketQuery)
        .filter(
            _in_scope(SavedTicketQuery.owner_id, user.id if user else None),
            _in_scope(SavedTicketQuery.project_id, target_project_id),
            SavedTicketQuery.destination == row.destination,
            SavedTicketQuery.name == wanted,
        )
        .first()
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
        project_id=target_project_id,
    )
