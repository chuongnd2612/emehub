"""Audit endpoints.

``POST /audit/events`` is in the integration contract (INTEGRATION.md §3): an
agent appends an event attributed to itself. The attribution is taken from the
caller's **token**, never from the body — ``source`` is the token's ``aud`` and
``actorId`` is its ``sub``, so a DAgent token cannot append an event that claims
to come from the hub or from another user.

``GET /audit/events`` is the hub's own read side, scoped by
``app.services.ownership`` — a member sees their own events plus the shared
namespace, never another member's.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps_auth import require_principal, require_user
from app.models.audit import AUDIT_ACTOR_TYPES, AUDIT_CATEGORIES, AUDIT_STATUSES
from app.models.user import User
from app.schemas import AuditEventIn, AuditEventOut, OkResponse
from app.services import audit_service

router = APIRouter(prefix="/audit", tags=["audit"])


@router.post("/events", response_model=OkResponse, status_code=201)
def append_event(
    body: AuditEventIn,
    principal: User = Depends(require_principal),
    db: Session = Depends(get_db),
) -> OkResponse:
    if body.category not in AUDIT_CATEGORIES:
        raise HTTPException(status_code=400, detail=f"Unknown category '{body.category}'")
    if body.actor_type not in AUDIT_ACTOR_TYPES:
        raise HTTPException(status_code=400, detail=f"Unknown actorType '{body.actor_type}'")
    if body.status not in AUDIT_STATUSES:
        raise HTTPException(status_code=400, detail=f"Unknown status '{body.status}'")
    if not (body.action or "").strip():
        raise HTTPException(status_code=400, detail="action is required")
    audit_service.record(
        category=body.category,
        action=body.action,
        actor_type=body.actor_type,
        actor=principal.email,
        actor_id=principal.id,
        # From the token, not the body.
        source=getattr(principal, "_aud", None),
        target=body.target,
        status=body.status,
        meta=body.meta,
        detail=body.detail,
        owner_id=principal.id,
        db=db,
    )
    return OkResponse()


@router.get("/events", response_model=list[AuditEventOut])
def list_events(
    category: str | None = Query(default=None),
    source: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
) -> list[AuditEventOut]:
    rows = audit_service.list_events(
        db, user, category=category, source=source, limit=limit, offset=offset
    )
    return [AuditEventOut.model_validate(r) for r in rows]
