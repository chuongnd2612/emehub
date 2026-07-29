"""Tickets router — the hub's ticket store (INTEGRATION.md §3, ROADMAP Phase 4).

    GET    /tickets                  -> TicketPageOut    (paged, filterable)
    GET    /tickets/{external_id}    -> TicketDetailOut
    POST   /tickets/sync             -> SyncResult       (pull from a provider)
    DELETE /tickets/{external_id}    -> 204              (local delete only)

## Posture: CONTRACT

Two of these four endpoints are in the integration contract, and **agents are
the primary consumer** — QAgent and DAgent read work items from the hub instead
of each discovering them per run. An agent calls with the token it holds
(``aud: "qagent"`` / ``"dagent"``), so a hub-audience-only gate would make the
contract unusable. The router is therefore registered ``CONTRACT``
(``Depends(require_principal)``): any *registered* audience passes, an
unregistered one still does not.

Sync and delete sit behind the same gate deliberately. Both are scoped to the
caller's own rows — sync pulls through the caller's own connection and upserts
into the caller's own tickets; delete removes only a row the caller can already
see, and is local-only (it never touches the provider, so a re-sync restores
it). Neither is a hub-administration action, so neither needs ``aud: emehub``.

## Scoping

Every read and write goes through ``app.services.ownership``: a member sees
their own tickets plus the shared (``owner_id IS NULL``) namespace, and never
another member's. A ticket owned by someone else 404s rather than 403s — a 403
would confirm it exists.

The schemas live in this module rather than in ``app/schemas.py`` so the slice
stays file-disjoint from the other Phase 4 slices; they use the shared
``ApiModel`` base, so the wire stays camelCase like everything else.
"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import Field
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps_auth import require_principal
from app.models.user import User
from app.schemas import ApiModel
from app.services import audit_service, ticket_service

router = APIRouter(prefix="/tickets", tags=["tickets"])


# ---------------------------------------------------------------- schemas
class TicketOut(ApiModel):
    """List shape — the summary fields, without the heavy JSON payloads."""

    id: int
    external_id: str
    provider_kind: str = ""
    project_id: int | None = None
    connection_id: int | None = None
    title: str = ""
    work_item_type: str = ""
    status: str = ""
    priority: str = ""
    assignee: str = ""
    sprint: str = ""
    area_path: str = ""
    epic: str = ""
    labels: list = Field(default_factory=list)
    ac_count: int = 0
    synced_at: datetime | None = None


class TicketDetailOut(TicketOut):
    """Detail shape — everything the provider gave us, normalised."""

    description: str = ""
    acceptance_criteria: list = Field(default_factory=list)
    acceptance_criteria_html: str = ""
    comments: list = Field(default_factory=list)
    attachments: list = Field(default_factory=list)
    linked_prs: list = Field(default_factory=list)


class TicketPageOut(ApiModel):
    items: list[TicketOut] = Field(default_factory=list)
    total: int = 0
    page: int = 1
    page_size: int = 25


class SyncRequest(ApiModel):
    """Which connection to pull through, and which work items to pull.

    ``connectionId`` wins; ``providerKind`` is the fallback ("the first
    work-item connection of this kind that I can see").
    """

    connection_id: int | None = None
    provider_kind: str | None = None
    mode: str = "sprint"
    sprint: str | None = None
    sprint_path: str | None = None
    area_path: str | None = None
    states: list[str] = Field(default_factory=list)
    work_item_types: list[str] = Field(default_factory=list)
    ticket_ids: list[str] = Field(default_factory=list)
    #: The provider-side project name, overriding the connection's default.
    project: str | None = None
    #: The hub project registry row to attribute the synced tickets to.
    project_id: int | None = None


class SyncResult(ApiModel):
    synced: int = 0
    tickets: list[TicketOut] = Field(default_factory=list)


def _csv(value: str | None) -> list[str]:
    return [part.strip() for part in (value or "").split(",") if part.strip()]


# ---------------------------------------------------------------- endpoints
@router.get("", response_model=TicketPageOut)
def list_tickets(
    # Multi-word query params are camelCase on the wire, matching the rest of the
    # API; FastAPI needs the explicit alias to bind the snake_case handler args.
    project_id: int | None = Query(None, alias="projectId"),
    provider_kind: str | None = Query(None, alias="providerKind"),
    connection_id: int | None = Query(None, alias="connectionId"),
    status: str | None = None,
    assignee: str | None = None,
    sprint: str | None = None,
    area_path: str | None = Query(None, alias="areaPath"),
    states: str | None = Query(None, description="Comma-separated"),
    work_item_types: str | None = Query(None, alias="workItemTypes"),
    priority: str | None = None,
    epic: str | None = None,
    q: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(25, alias="pageSize", ge=1, le=200),
    principal: User = Depends(require_principal),
    db: Session = Depends(get_db),
) -> TicketPageOut:
    items, total = ticket_service.list_tickets(
        db,
        principal,
        project_id=project_id,
        provider_kind=provider_kind,
        connection_id=connection_id,
        status=status,
        assignee=assignee,
        sprint=sprint,
        area_path=area_path,
        states=_csv(states),
        work_item_types=_csv(work_item_types),
        priority=priority,
        epic=epic,
        q=q,
        page=page,
        page_size=page_size,
    )
    return TicketPageOut(
        items=[TicketOut.model_validate(t) for t in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/{external_id}", response_model=TicketDetailOut)
def get_ticket(
    external_id: str,
    provider_kind: str | None = Query(None, alias="providerKind"),
    principal: User = Depends(require_principal),
    db: Session = Depends(get_db),
) -> TicketDetailOut:
    ticket = ticket_service.get_ticket(db, principal, external_id, provider_kind=provider_kind)
    if ticket is None:
        raise HTTPException(status_code=404, detail=f"Ticket '{external_id}' not found")
    return TicketDetailOut.model_validate(ticket)


@router.post("/sync", response_model=SyncResult)
def sync_tickets(
    body: SyncRequest,
    principal: User = Depends(require_principal),
    db: Session = Depends(get_db),
) -> SyncResult:
    """Pull work items through the caller's connection and upsert them.

    Upsert, not insert: re-syncing the same work item updates the existing row,
    keyed on ``(owner scope, provider_kind, external_id)``.
    """
    try:
        synced, resolved = ticket_service.sync_tickets(
            db,
            principal,
            connection_id=body.connection_id,
            provider_kind=body.provider_kind,
            mode=body.mode,
            sprint=body.sprint,
            sprint_path=body.sprint_path,
            area_path=body.area_path,
            states=body.states or None,
            work_item_types=body.work_item_types or None,
            ticket_ids=body.ticket_ids or None,
            project=body.project,
            project_id=body.project_id,
        )
    except ticket_service.TicketSyncUnavailable as exc:
        # Not wired to the provider adapters in this deployment. 503 and say so —
        # never a 200 with zero tickets, which reads as "the sprint is empty".
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ticket_service.TicketSourceError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    audit_service.record(
        category="ticket",
        action="Synced tickets",
        actor_type="user",
        actor=principal.email,
        actor_id=principal.id,
        source=getattr(principal, "_aud", None),
        target=body.sprint or resolved.label or resolved.provider_kind,
        meta=f"{len(synced)} work items",
        owner_id=principal.id,
        db=db,
    )
    return SyncResult(synced=len(synced), tickets=[TicketOut.model_validate(t) for t in synced])


@router.delete("/{external_id}", status_code=204, response_class=Response)
def delete_ticket(
    external_id: str,
    principal: User = Depends(require_principal),
    db: Session = Depends(get_db),
) -> Response:
    """Local delete. The provider is never called, so a re-sync restores it."""
    if not ticket_service.delete_ticket(db, principal, external_id):
        raise HTTPException(status_code=404, detail=f"Ticket '{external_id}' not found")
    audit_service.record(
        category="ticket",
        action="Removed ticket",
        actor_type="user",
        actor=principal.email,
        actor_id=principal.id,
        source=getattr(principal, "_aud", None),
        target=external_id,
        owner_id=principal.id,
        db=db,
    )
    return Response(status_code=204)
