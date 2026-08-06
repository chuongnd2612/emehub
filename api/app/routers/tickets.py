"""Tickets router — the hub's ticket store (INTEGRATION.md §3, ROADMAP Phase 4).

    GET    /tickets                             -> TicketPageOut  (paged, filterable)
    GET    /tickets/{external_id}               -> TicketDetailOut
    GET    /tickets/{external_id}/comments      -> CommentListOut  (live, via the hub's PAT)
    GET    /tickets/{external_id}/test-cases    -> TestCaseListOut (live, via the hub's PAT)
    POST   /tickets/{external_id}/comments      -> 201             (write to the provider)
    POST   /tickets/{external_id}/state         -> TicketDetailOut (write to the provider)
    POST   /tickets/{external_id}/test-cases    -> 201             (write to the provider)
    POST   /tickets/sync                        -> SyncResult      (pull from a provider)
    DELETE /tickets/{external_id}               -> 204             (local delete only)

Everything that touches a provider goes through ``services.ticket_provider``; read
its module docstring for why an empty list is never allowed to mean three
different things, and why the writes mirror into the ticket row.

The three writes are what let an agent stop holding provider credentials: they are
the provider side of QAgent's Publish and Link screens, performed here so the PAT
never leaves.

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
from pydantic import ConfigDict, Field
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps_auth import require_principal
from app.models.user import User
from app.schemas import ApiModel
from app.services import (
    audit_service,
    connection_service,
    ticket_provider,
    ticket_query,
    ticket_service,
)

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

    ## Two ways to say what to pull, and no third

    Either ``query`` — a clause query, compiled per provider — or ``ticketIds``, an
    explicit selection of known work items. The legacy
    ``mode``/``sprint``/``sprintPath``/``areaPath``/``states``/``workItemTypes``
    fields are **gone** (#130): they were a filter language expressing a fraction of
    what a clause query can, and every one of them is now a clause. See
    ``docs/INTEGRATION.md`` §3 for the mapping.

    ``ticketIds`` survives because selecting known items is **not** filtering: the
    clause model has no id field, and giving it one would let a list pretend to be a
    query.

    One of the two is required. "Everything in the project" is expressible — a query
    of ``state is not Removed``, which is what the Import dialog's *All open work
    items* sends — but it has to be *asked for*, not arrived at by omitting
    everything.
    """

    model_config = ConfigDict(extra="forbid", **ApiModel.model_config)

    connection_id: int | None = None
    provider_kind: str | None = None
    #: External ids of known work items. Ignored when ``query`` is given.
    ticket_ids: list[str] = Field(default_factory=list)
    #: The provider-side project name, overriding the connection's default.
    project: str | None = None
    #: The hub project registry row to attribute the synced tickets to.
    project_id: int | None = None
    #: A clause query (`services.ticket_query`), validated against the destination's
    #: capability matrix before anything is compiled.
    query: dict | None = None


class QueryPreviewRequest(ApiModel):
    """Ask the provider what a query would return, without importing it."""

    model_config = ConfigDict(extra="forbid", **ApiModel.model_config)

    connection_id: int | None = None
    provider_kind: str | None = None
    project: str | None = None
    query: dict = Field(default_factory=dict)


class QueryPreviewResult(ApiModel):
    #: How many work items the provider matched.
    total: int = 0
    #: A short sample — enough to confirm the shape, not to read the result.
    sample: list[TicketOut] = Field(default_factory=list)
    #: The query in words, for the confirmation line.
    description: str = ""


class SyncResult(ApiModel):
    synced: int = 0
    tickets: list[TicketOut] = Field(default_factory=list)


class CommentOut(ApiModel):
    """One provider comment. Same shape as the ``comments`` snapshot on
    ``TicketDetailOut``, so an agent handles one shape, not two."""

    who: str = ""
    when: str = ""
    text: str = ""


class CommentListOut(ApiModel):
    items: list[CommentOut] = Field(default_factory=list)
    #: ``False`` when the provider has no comment concept — an empty list then
    #: means "not supported", not "there are none". See ``ticket_provider``.
    supported: bool = True


class TestCaseOut(ApiModel):
    external_id: str = ""
    title: str = ""
    state: str = ""


class TestCaseListOut(ApiModel):
    items: list[TestCaseOut] = Field(default_factory=list)
    supported: bool = True
    #: ``True`` when the provider answered project-wide rather than for this
    #: ticket alone (Azure DevOps always does). A caller that assumes scoping
    #: would otherwise silently over-count.
    project_wide: bool = False


class PublishCommentIn(ApiModel):
    body: str = Field(min_length=1)
    #: Provider-side attachment references. Passed through; adapters that have no
    #: attachment path ignore them.
    attachments: list[str] = Field(default_factory=list)


class PublishCommentOut(ApiModel):
    external_comment_id: str = ""


class TransitionIn(ApiModel):
    target_status: str = Field(min_length=1)


class CaseIn(ApiModel):
    title: str = Field(min_length=1)
    precondition: str = ""
    #: ``[{"a": action, "e": expected}]`` — the shape ``create_test_case`` takes.
    steps: list[dict] = Field(default_factory=list)
    priority: str = "Medium"


class CreateTestCasesIn(ApiModel):
    cases: list[CaseIn] = Field(min_length=1)
    #: Link each created case back to the work item where the provider supports it.
    link: bool = True


class CaseResultOut(ApiModel):
    title: str = ""
    external_id: str = ""
    url: str = ""
    status: str = ""
    linked: bool = False
    #: The provider's own reason, when this case failed. Empty on success.
    error: str = ""


class CreateTestCasesOut(ApiModel):
    created: list[CaseResultOut] = Field(default_factory=list)
    #: How many of ``cases`` actually landed. Partial success is normal, so a 2xx
    #: does **not** mean everything worked — read this, or each ``error``.
    succeeded: int = 0
    failed: int = 0


def _csv(value: str | None) -> list[str]:
    return [part.strip() for part in (value or "").split(",") if part.strip()]


def _ticket_or_404(
    db: Session, principal: User, external_id: str, provider_kind: str | None
):
    ticket = ticket_service.get_ticket(db, principal, external_id, provider_kind=provider_kind)
    if ticket is None:
        raise HTTPException(status_code=404, detail=f"Ticket '{external_id}' not found")
    return ticket


def _provider_read(call, db: Session, ticket):
    """Run a ``ticket_provider`` read and map its failures to status codes.

    The mapping is the point: `INTEGRATION.md` §5 requires a failed read to be
    distinguishable from an empty one, so nothing here can answer ``200`` with an
    empty list because the provider was unreachable.
    """
    try:
        return call(db, ticket)
    except ticket_provider.NoWorkItemConnection as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ticket_provider.AdapterLayerMissing as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ticket_provider.ProviderUnavailable as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


def _provider_write_error(exc: Exception) -> HTTPException:
    """The status code for a failed provider write.

    Same mapping as the reads. A rejected write — an unresolvable target state, a
    transition the workflow does not offer — arrives as ``ProviderUnavailable``
    and surfaces as ``502`` carrying **the provider's own reason**, because that
    reason is the only actionable part and an agent shows it to a human.
    """
    if isinstance(exc, HTTPException):
        return exc
    if isinstance(exc, ticket_provider.NoWorkItemConnection):
        return HTTPException(status_code=404, detail=str(exc))
    if isinstance(exc, ticket_provider.AdapterLayerMissing):
        return HTTPException(status_code=503, detail=str(exc))
    return HTTPException(status_code=502, detail=str(exc))


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
    return TicketDetailOut.model_validate(
        _ticket_or_404(db, principal, external_id, provider_kind)
    )


@router.get("/{external_id}/comments", response_model=CommentListOut)
def list_ticket_comments(
    external_id: str,
    provider_kind: str | None = Query(None, alias="providerKind"),
    principal: User = Depends(require_principal),
    db: Session = Depends(get_db),
) -> CommentListOut:
    """This work item's comment thread, read live from the provider.

    The hub holds the PAT and makes the call, so an agent needs no provider
    credential of its own — the same arrangement as ``POST /tickets/sync``.

    Distinct from the ``comments`` field on ``GET /tickets/{id}``, which is the
    snapshot taken at ``syncedAt``. Same shape, different freshness.
    """
    read = _provider_read(ticket_provider.list_comments, db, _ticket_or_404(
        db, principal, external_id, provider_kind
    ))
    return CommentListOut(
        items=[CommentOut.model_validate(c) for c in read.items],
        supported=read.supported,
    )


@router.get("/{external_id}/test-cases", response_model=TestCaseListOut)
def list_ticket_test_cases(
    external_id: str,
    provider_kind: str | None = Query(None, alias="providerKind"),
    principal: User = Depends(require_principal),
    db: Session = Depends(get_db),
) -> TestCaseListOut:
    """Provider-side test cases, for continuing existing numbering when generating.

    **Check ``projectWide``.** Azure DevOps answers for the whole project rather
    than this work item, so treating the result as scoped over-counts.
    """
    read = _provider_read(ticket_provider.list_test_cases, db, _ticket_or_404(
        db, principal, external_id, provider_kind
    ))
    return TestCaseListOut(
        items=[TestCaseOut.model_validate(c) for c in read.items],
        supported=read.supported,
        project_wide=read.project_wide,
    )


# ------------------------------------------------------------- provider writes
def _audit_write(
    principal: User, db: Session, *, action: str, target: str, status: str, meta: str = ""
) -> None:
    """Record an agent-initiated provider write.

    These are the first writes an agent causes to leave the hub for a third
    party, so the audit row is the only record that it happened. ``source`` is the
    calling audience, so a comment posted by QAgent is distinguishable from one
    posted in the hub UI.
    """
    audit_service.record(
        category="ticket",
        action=action,
        actor_type="user",
        actor=principal.email,
        actor_id=principal.id,
        source=getattr(principal, "_aud", None),
        target=target,
        status=status,
        meta=meta,
        owner_id=principal.id,
        db=db,
    )


@router.post("/{external_id}/comments", response_model=PublishCommentOut, status_code=201)
def publish_ticket_comment(
    external_id: str,
    payload: PublishCommentIn,
    provider_kind: str | None = Query(None, alias="providerKind"),
    principal: User = Depends(require_principal),
    db: Session = Depends(get_db),
) -> PublishCommentOut:
    """Post a comment on the work item, through the hub's own PAT.

    Separate from the transition below on purpose: QAgent's publish flow posts a
    comment and *then* transitions, and has to be able to report a comment that
    published while its transition failed. One combined endpoint could not express
    that state.
    """
    ticket = _ticket_or_404(db, principal, external_id, provider_kind)
    try:
        comment_id = ticket_provider.publish_comment(
            db,
            ticket,
            body=payload.body,
            attachments=payload.attachments or None,
            author=principal.email,
        )
    except Exception as exc:
        _audit_write(
            principal,
            db,
            action="Posted a comment",
            target=external_id,
            status="error",
            meta=str(exc)[:200],
        )
        raise _provider_write_error(exc) from exc
    _audit_write(principal, db, action="Posted a comment", target=external_id, status="success")
    return PublishCommentOut(external_comment_id=comment_id)


@router.post("/{external_id}/state", response_model=TicketDetailOut)
def transition_ticket(
    external_id: str,
    payload: TransitionIn,
    provider_kind: str | None = Query(None, alias="providerKind"),
    principal: User = Depends(require_principal),
    db: Session = Depends(get_db),
) -> TicketDetailOut:
    """Transition the work item, and bring the hub's own row into line.

    Returns the ticket as the hub now holds it. The local row is updated **only**
    after the provider accepted the transition — a rejected transition leaves the
    stored status untouched rather than recording a state the provider never
    reached.
    """
    ticket = _ticket_or_404(db, principal, external_id, provider_kind)
    try:
        updated = ticket_provider.transition(db, ticket, target_status=payload.target_status)
    except Exception as exc:
        _audit_write(
            principal,
            db,
            action=f"Transitioned to '{payload.target_status}'",
            target=external_id,
            status="error",
            meta=str(exc)[:200],
        )
        raise _provider_write_error(exc) from exc
    _audit_write(
        principal,
        db,
        action=f"Transitioned to '{payload.target_status}'",
        target=external_id,
        status="success",
    )
    return TicketDetailOut.model_validate(updated)


@router.post("/{external_id}/test-cases", response_model=CreateTestCasesOut, status_code=201)
def create_ticket_test_cases(
    external_id: str,
    payload: CreateTestCasesIn,
    provider_kind: str | None = Query(None, alias="providerKind"),
    principal: User = Depends(require_principal),
    db: Session = Depends(get_db),
) -> CreateTestCasesOut:
    """Create provider-side test cases for this work item, in one pass.

    **Batched, and partially successful by design.** An agent creates every case
    for a ticket together, and one rejected case must not discard the ones already
    created — so this answers ``201`` with a per-case outcome, and the caller reads
    ``failed`` or each ``error``. A failure that stops *any* case being attempted
    (unroutable ticket, undecryptable PAT) is still a 4xx/5xx.
    """
    ticket = _ticket_or_404(db, principal, external_id, provider_kind)
    requested = [
        ticket_provider.CaseRequest(
            title=case.title,
            precondition=case.precondition,
            steps=case.steps,
            priority=case.priority,
        )
        for case in payload.cases
    ]
    try:
        results = ticket_provider.create_test_cases(
            db, ticket, cases=requested, link=payload.link
        )
    except Exception as exc:
        _audit_write(
            principal,
            db,
            action="Created test cases",
            target=external_id,
            status="error",
            meta=str(exc)[:200],
        )
        raise _provider_write_error(exc) from exc

    failed = sum(1 for r in results if r.error)
    _audit_write(
        principal,
        db,
        action="Created test cases",
        target=external_id,
        status="warning" if failed else "success",
        meta=f"{len(results) - failed} created, {failed} failed",
    )
    return CreateTestCasesOut(
        created=[CaseResultOut.model_validate(r._asdict()) for r in results],
        succeeded=len(results) - failed,
        failed=failed,
    )


def _destination(
    db: Session,
    principal: User,
    *,
    connection_id: int | None,
    provider_kind: str | None,
) -> str:
    """Which capability matrix this request is to be judged against.

    ``provider_kind`` is already a destination name (``azure_devops`` | ``jira`` |
    ``github``), so it is used as given. When only a ``connectionId`` was sent the
    kind has to come **from the connection**: defaulting to Azure DevOps would judge
    a Jira query against WIQL's matrix, accept an ``areaPath`` clause Jira cannot
    express, and only fail later at the compiler — the exact silent-mismatch this
    matrix exists to make impossible.
    """
    kind = (provider_kind or "").strip()
    if kind:
        return kind
    if connection_id is not None:
        connection = connection_service.get_connection(db, connection_id, principal.id)
        if connection is not None:
            return connection.kind
    return "azure_devops"


def _compiled(raw: dict | None, destination: str | None) -> ticket_query.TicketQuery | None:
    """Parse and validate a wire query, or 422 with what is wrong.

    The same `validate` the client runs to grey out Apply — so a request the client
    would not have sent is refused here rather than compiled into something the
    provider misreads.
    """
    if not raw:
        return None
    spec = ticket_query.query_from_wire(raw)
    where = (destination or "").strip() or "azure_devops"
    problems = ticket_query.validate(spec, where)
    if problems:
        raise HTTPException(
            status_code=422,
            detail={"problems": [p.as_dict() for p in problems]},
        )
    return spec


class TicketSearchRequest(ApiModel):
    """A clause query over the hub's own mirror, paged.

    A POST rather than more parameters on ``GET /tickets``: a clause list does not
    fit a query string honestly — JSON in a parameter is length-limited and awful
    to read in a log — and `GET /tickets` is a CONTRACT route agents already call,
    which stays exactly as it is.
    """

    model_config = ConfigDict(extra="forbid", **ApiModel.model_config)

    query: dict = Field(default_factory=dict)
    #: Free text over id / title / project. A different thing from a `title
    #: contains` clause, and kept separate because that is how the toolbar reads.
    q: str | None = None
    provider_kind: str | None = None
    project_id: int | None = None
    page: int = 1
    page_size: int = 25


@router.post("/search", response_model=TicketPageOut)
def search_tickets(
    body: TicketSearchRequest,
    principal: User = Depends(require_principal),
    db: Session = Depends(get_db),
) -> TicketPageOut:
    """One page of the mirror, narrowed by a clause query.

    The ``mirror`` destination: parameterised SQL over our own columns, so nothing
    here builds a query string. Scoping is unchanged — a member sees their own rows
    plus the shared namespace, and an ``any`` query widens within that and never
    past it.
    """
    spec = _compiled(body.query, "mirror") if body.query else None
    items, total = ticket_service.list_tickets(
        db,
        principal,
        provider_kind=body.provider_kind,
        project_id=body.project_id,
        q=body.q,
        spec=spec,
        page=body.page,
        page_size=body.page_size,
    )
    return TicketPageOut(
        items=[TicketOut.model_validate(t) for t in items],
        total=total,
        page=max(body.page, 1),
        page_size=body.page_size,
    )


@router.post("/query/preview", response_model=QueryPreviewResult)
def preview_query(
    body: QueryPreviewRequest,
    principal: User = Depends(require_principal),
    db: Session = Depends(get_db),
) -> QueryPreviewResult:
    """What this query would import, without importing it.

    The hub runs the provider call with its own stored PAT, exactly as
    `POST /tickets/sync` does — the caller never holds a credential. Nothing is
    written, so this is safe to run on every Apply.
    """
    spec = _compiled(
        body.query,
        _destination(
            db,
            principal,
            connection_id=body.connection_id,
            provider_kind=body.provider_kind,
        ),
    )
    try:
        total, sample, _resolved = ticket_service.preview_tickets(
            db,
            principal,
            connection_id=body.connection_id,
            provider_kind=body.provider_kind,
            spec=spec,
            project=body.project,
        )
    except ticket_service.TicketSyncUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ticket_service.TicketSourceError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return QueryPreviewResult(
        total=total,
        sample=[TicketOut.model_validate(_preview_row(item)) for item in sample],
        description=ticket_query.describe(spec) if spec else "everything in the project",
    )


def _preview_row(item: dict) -> dict:
    """A fetched, unsaved work item in the shape `TicketOut` renders.

    Preview rows have no database identity — they have not been imported — so `id`
    is 0 and nothing downstream should treat one as a stored ticket.
    """
    return {
        "id": 0,
        "external_id": str(item.get("external_id", "")),
        "title": item.get("title", ""),
        "work_item_type": item.get("work_item_type", ""),
        "status": item.get("status", ""),
        "priority": item.get("priority", ""),
        "assignee": item.get("assignee", ""),
        "sprint": item.get("sprint", ""),
        "area_path": item.get("area_path", ""),
        "epic": item.get("epic", ""),
        "labels": item.get("labels", []),
    }


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
    if not body.query and not body.ticket_ids:
        # Refused rather than read as "everything". A sync that pulls a whole
        # project because a field was left out is expensive, surprising, and
        # indistinguishable from a caller that meant to send a filter.
        raise HTTPException(
            status_code=422,
            detail=(
                "Say what to import: a `query`, or `ticketIds` for known work items."
            ),
        )
    spec = _compiled(
        body.query,
        _destination(
            db,
            principal,
            connection_id=body.connection_id,
            provider_kind=body.provider_kind,
        ),
    )
    try:
        synced, resolved = ticket_service.sync_tickets(
            db,
            principal,
            connection_id=body.connection_id,
            provider_kind=body.provider_kind,
            ticket_ids=body.ticket_ids or None,
            project=body.project,
            project_id=body.project_id,
            spec=spec,
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
        target=resolved.label or resolved.provider_kind,
        # What was asked for, in words, rather than only how much came back. The
        # audit row used to carry the sprint name; a query in prose is the same
        # information for a selection that is no longer one field.
        meta=(
            f"{len(synced)} work items · {ticket_query.describe(spec)}"
            if spec is not None
            else f"{len(synced)} work items · {len(body.ticket_ids)} named"
        ),
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
