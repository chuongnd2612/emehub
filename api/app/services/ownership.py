"""Workspace scoping — QAgent's ``owner_id`` + shared convention.

Every scoped table carries a nullable ``owner_id`` FK to ``users.id``:

* ``owner_id = <user>`` — private to that user.
* ``owner_id IS NULL`` — the **workspace-wide shared namespace**, visible to
  everyone in the hub.

There is no organisation or team entity; that was an explicit product decision
(INTEGRATION.md › Open items, resolved in favour of inheriting this convention).

These three helpers are the only place ownership is checked or applied, so the
later per-domain slices (credentials, connections, projects, knowledge) stay
consistent instead of each router re-implementing the rule.

**Fail closed.** QAgent's version treats ``user is None`` as "no scoping" and
returns everything — a deliberate migration bridge for a codebase where auth was
optional. The hub has no such mode (CLAUDE.md › Never fail open), so a missing
user here yields *nothing*, not *everything*.
"""

from __future__ import annotations

from typing import TypeVar

from fastapi import HTTPException
from sqlalchemy import false, or_
from sqlalchemy.orm import Query, Session

from app.models.user import ROLE_ADMIN, User

ModelT = TypeVar("ModelT")


def owned(query: Query[ModelT], model: type[ModelT], user: User | None) -> Query[ModelT]:
    """Restrict ``query`` to what ``user`` may see: their own rows **plus** the
    shared (``owner_id IS NULL``) namespace, and never another user's rows.

    ``model`` must declare an ``owner_id`` column. With no user the query is
    filtered to the empty set — an unauthenticated caller sees nothing.
    """
    if user is None:
        return query.filter(false())
    return query.filter(or_(model.owner_id == user.id, model.owner_id.is_(None)))


def _visible(obj: object, user: User | None) -> bool:
    """True when ``user`` may see ``obj``: shared rows are visible to everyone,
    owned rows only to their owner."""
    if user is None:
        return False
    owner_id = getattr(obj, "owner_id", None)
    return owner_id is None or owner_id == user.id


def get_owned_or_404(db: Session, model: type[ModelT], id: int, user: User | None) -> ModelT:
    """Fetch ``model`` by primary key, or 404.

    A row owned by a *different* user 404s rather than 403s — a 403 would confirm
    the row exists, which is itself a disclosure.
    """
    obj = db.get(model, id)
    if obj is None or not _visible(obj, user):
        raise HTTPException(status_code=404, detail=f"{model.__name__} not found")
    return obj


def check_owned_or_404(
    obj: object | None, user: User | None, *, not_found: str = "Not found"
) -> None:
    """Same check for rows looked up by something other than the primary key
    (a project ``key``, a provider ``kind``). No-op when ``obj`` is ``None`` —
    the caller decides whether absence is a 404."""
    if obj is not None and not _visible(obj, user):
        raise HTTPException(status_code=404, detail=not_found)


def stamp_owner(obj: ModelT, user: User | None) -> ModelT:
    """Set ``obj.owner_id`` to ``user.id``, returning ``obj`` for chaining.

    Passing ``None`` deliberately leaves the row in the **shared** namespace —
    that is the only way to create a workspace-wide resource, so it must be an
    explicit choice at the call site, not an accident of an absent user.
    """
    if user is not None:
        obj.owner_id = user.id
    return obj


def can_write_shared(user: User | None) -> bool:
    """Only admins may create or modify rows in the shared namespace."""
    return user is not None and user.role == ROLE_ADMIN
