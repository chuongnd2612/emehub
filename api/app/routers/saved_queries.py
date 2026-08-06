"""Saved ticket queries — `/ticket-queries`.

## Posture: CONTRACT

An agent builds and runs queries through `POST /tickets/sync` and
`POST /tickets/search`, so it has the same reason to read a saved one. Scoping is
the hub's usual rule: own rows plus the shared namespace, and a row owned by
someone else **404s rather than 403s** — a 403 would confirm it exists.

## A built-in is 409, not 403

A shipped preset may be used and copied but never edited or deleted. That is a
409 (a conflict with what the row *is*) rather than a 403 (a permission the caller
lacks) — the caller is not being denied, the request does not apply. The message
names the way forward: duplicate it and edit the copy. Which is what makes
read-only presets tolerable rather than a dead end.
"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import ConfigDict, Field
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps_auth import require_principal
from app.models.ticket_query_saved import SavedTicketQuery
from app.models.user import User
from app.schemas import ApiModel, OkResponse
from app.services import audit_service, saved_queries, ticket_query

router = APIRouter(prefix="/ticket-queries", tags=["ticket-queries"])


class SavedQueryOut(ApiModel):
    id: int
    name: str
    destination: str
    query: dict = Field(default_factory=dict)
    #: Re-derived from the query on write, so it cannot disagree with the clauses.
    description: str = ""
    #: Shipped preset: usable and copyable, never editable or deletable.
    built_in: bool = False
    #: True when it lives in the shared namespace rather than one member's.
    shared: bool = False
    created_at: datetime | None = None


class SavedQueryIn(ApiModel):
    model_config = ConfigDict(extra="forbid", **ApiModel.model_config)

    name: str = Field(min_length=1, max_length=120)
    destination: str
    query: dict = Field(default_factory=dict)
    #: Save into the shared namespace instead of your own.
    shared: bool = False


class SavedQueryPatch(ApiModel):
    model_config = ConfigDict(extra="forbid", **ApiModel.model_config)

    name: str | None = Field(default=None, min_length=1, max_length=120)
    query: dict | None = None


class DuplicateIn(ApiModel):
    model_config = ConfigDict(extra="forbid", **ApiModel.model_config)

    name: str | None = Field(default=None, min_length=1, max_length=120)


def _out(row: SavedTicketQuery) -> SavedQueryOut:
    return SavedQueryOut(
        id=row.id,
        name=row.name,
        destination=row.destination,
        query=dict(row.query or {}),
        description=row.description,
        built_in=row.built_in,
        shared=row.owner_id is None,
        created_at=row.created_at,
    )


def _validated(query: dict, destination: str) -> dict:
    """Refuse a query the destination cannot run, before it is ever saved.

    A saved query that fails the moment it is applied is worse than one that was
    never saved: the failure arrives later, somewhere else, with no clue why.
    """
    spec = ticket_query.query_from_wire(query)
    problems = ticket_query.validate(spec, destination)
    if problems:
        raise HTTPException(
            status_code=422, detail={"problems": [p.as_dict() for p in problems]}
        )
    return query


def _load(db: Session, user: User, query_id: int) -> SavedTicketQuery:
    row = saved_queries.get_query(db, user, query_id)
    if row is None:
        raise HTTPException(status_code=404, detail="No such saved query")
    return row


@router.get("", response_model=list[SavedQueryOut])
def list_saved(
    destination: str | None = Query(None),
    principal: User = Depends(require_principal),
    db: Session = Depends(get_db),
) -> list[SavedQueryOut]:
    """Presets first, then the caller's own. `?destination=` narrows to one.

    A query is not portable across providers — one naming `areaPath` cannot run on
    Jira — so a caller filters to where it intends to run it.
    """
    return [_out(row) for row in saved_queries.list_queries(db, principal, destination=destination)]


@router.post("", response_model=SavedQueryOut, status_code=201)
def create_saved(
    body: SavedQueryIn,
    principal: User = Depends(require_principal),
    db: Session = Depends(get_db),
) -> SavedQueryOut:
    _validated(body.query, body.destination)
    try:
        row = saved_queries.create_query(
            db,
            principal,
            name=body.name.strip(),
            destination=body.destination,
            query=body.query,
            shared=body.shared,
        )
    except saved_queries.DuplicateName as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    audit_service.record(
        category="ticket",
        action="Saved a ticket query",
        actor=principal.email,
        actor_id=principal.id,
        actor_type="user",
        source=getattr(principal, "_aud", None),
        target=row.name,
        owner_id=principal.id,
        db=db,
    )
    return _out(row)


@router.patch("/{query_id}", response_model=SavedQueryOut)
def update_saved(
    query_id: int,
    body: SavedQueryPatch,
    principal: User = Depends(require_principal),
    db: Session = Depends(get_db),
) -> SavedQueryOut:
    row = _load(db, principal, query_id)
    if body.query is not None:
        _validated(body.query, row.destination)
    try:
        updated = saved_queries.update_query(
            db, row, name=body.name.strip() if body.name else None, query=body.query
        )
    except saved_queries.BuiltInIsReadOnly as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return _out(updated)


@router.delete("/{query_id}", response_model=OkResponse)
def delete_saved(
    query_id: int,
    principal: User = Depends(require_principal),
    db: Session = Depends(get_db),
) -> OkResponse:
    row = _load(db, principal, query_id)
    try:
        saved_queries.delete_query(db, row)
    except saved_queries.BuiltInIsReadOnly as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return OkResponse()


@router.post("/{query_id}/duplicate", response_model=SavedQueryOut, status_code=201)
def duplicate_saved(
    query_id: int,
    body: DuplicateIn | None = None,
    principal: User = Depends(require_principal),
    db: Session = Depends(get_db),
) -> SavedQueryOut:
    """A copy the caller owns, always editable — including from a built-in.

    This is the answer to "I want that preset but slightly different", and the
    reason a read-only preset is not a dead end.
    """
    row = _load(db, principal, query_id)
    copy = saved_queries.duplicate_query(
        db, principal, row, name=body.name.strip() if body and body.name else None
    )
    return _out(copy)
