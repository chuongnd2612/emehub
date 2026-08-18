"""DAgent router — every endpoint the ticket-executor agent consumes, in one place.

    GET  /dagent/connections                                  -> list[DagentConnectionOut]
    (the PAT itself stays at the existing GET /connections/{id}/secret — see below)
    GET  /dagent/connections/{id}/projects                    -> list[DagentProjectOut]
    GET  /dagent/connections/{id}/sprints?project=            -> SprintListOut
    GET  /dagent/connections/{id}/tickets?project=&sprint=&scope= -> TicketListOut
    GET  /dagent/connections/{id}/tickets/{ext}/comments      -> CommentListOut
    GET  /dagent/connections/{id}/tickets/{ext}/states        -> StateListOut
    GET  /dagent/connections/{id}/tickets/{ext}/status        -> StatusOut
    POST /dagent/connections/{id}/tickets/{ext}/status        -> StatusOut
    GET  /dagent/connections/{id}/pull-request                -> ReviewOut
    POST /dagent/connections/{id}/pull-request/review-summaries -> ReviewSummaryListOut
    GET  /dagent/connections/{id}/pull-request/commits        -> CommitListOut
    GET  /dagent/connections/{id}/pull-request/commits/{sha}  -> CommitFileListOut
    POST /dagent/connections/{id}/pull-request/outcomes       -> OutcomeListOut

## Why a separate prefix

DAgent needs a wider provider surface than any other consumer — pull requests
above all — and needs work items at a fidelity the hub's ticket store does not
keep. Serving that by widening the existing routers would mean changing
endpoints QAgent and the hub UI already depend on, and changing an endpoint two
other consumers rely on in order to add a third is how a contract stops being
one.

So this router is **purely additive**. Nothing here modifies an existing route,
an existing schema or an existing service; registering it in ``main.ROUTERS`` is
the only edit outside this file and ``services/dagent_provider.py``. A
deployment that never calls ``/dagent/*`` behaves exactly as it did before this
router existed, which is what makes DAgent's own feature flag safe to leave off.

It also means one obvious place to look. Every hub endpoint DAgent talks to is
in this file, with **one deliberate exception**: the credential itself stays at
the existing ``GET /connections/{id}/secret``. DAgent still needs the raw PAT for
one thing — the Claude CLI reaches the provider over MCP, which the hub does not
proxy — and that endpoint is already the single audited crossing designed for it
(ADR 0010). Duplicating a secret-bearing route under this prefix would mean two
places a provider credential can leave the hub, and two audit paths to keep
honest, to save a caller one base path. It is not worth it.

## Posture: CONTRACT

Registered ``CONTRACT`` in ``main.ROUTERS`` (``Depends(require_principal)``):
DAgent calls with the token it holds, whose ``aud`` is ``"dagent"``, so
``require_user`` would refuse the only caller these exist for. An unregistered
audience is still refused, by the blanket dependency and by the guard
middleware.

**Every route here is scoped through ``get_owned_or_404``**, exactly like the
connections router: a member reaches their own connections plus the shared
namespace and never another member's, and another member's 404s rather than
403s — a 403 would confirm it exists.

These endpoints spend the hub's PAT against the provider, and that is the point
rather than a compromise. It is the same arrangement ``POST /tickets/sync``
already uses (INTEGRATION.md §3): the caller names a **connection**, never a
URL, so the hub picks the upstream from data it owns. That is what separates
this from the generic ``POST /connections/{id}/proxy``, which stays deferred
because a caller-directed forwarder is an SSRF and header-leak surface. Nothing
here takes a URL from the caller except ``/pull-request/outcomes``, and those
are parsed for a repository and PR id and then discarded — the request is built
from the connection's own base URL, never from the string that arrived.

## Failures are never an empty list

A read that failed and a read that found nothing must not look the same
(INTEGRATION.md §5), so every handler maps its exception:

* ``ProviderUnavailable`` -> 404. A routing gap: wrong connection kind, no
  project, nothing linked.
* ``ProviderError``       -> 502, carrying the provider's own reason, which is
  the only actionable part.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import Field
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps_auth import require_principal
from app.logging import logger
from app.models.provider_connection import WORK_ITEM, ProviderConnection
from app.models.user import User
from app.schemas import ApiModel
from app.services import connection_service, dagent_provider
from app.services.adapters.base import ProviderError
from app.services.dagent_provider import ProviderUnavailable
from app.services.ownership import get_owned_or_404

router = APIRouter(prefix="/dagent", tags=["dagent"])


# ----------------------------------------------------------------- schemas
class DagentConnectionOut(ApiModel):
    """The catalogue row. Same no-PAT rule as ``GET /connections``: ``hasPat``
    is the entire truth a response is allowed to tell about the credential."""

    id: int
    kind: str
    label: str = ""
    base_url: str = ""
    project: str = ""
    capabilities: list[str] = Field(default_factory=list)
    has_pat: bool = False


class DagentProjectOut(ApiModel):
    id: str = ""
    name: str = ""
    description: str = ""


class SprintOut(ApiModel):
    #: The classification node's identifier. Carried so a caller can key a list
    #: on something stable — two releases may each hold a "Sprint 1".
    id: str = ""
    name: str = ""
    #: The rooted ``System.IterationPath``. **This** is what to pass back as
    #: ``sprint`` on ``/tickets``: the name alone is not a path, and ADO rejects
    #: a query built from one outright rather than matching nothing.
    path: str = ""
    start_date: str = ""
    finish_date: str = ""
    #: "past" | "current" | "future", as **ADO classifies it** for the team these
    #: iterations belong to. Not derived from the dates here: a project-wide
    #: iteration tree has several sprints spanning today, one per team sub-tree,
    #: so a date comparison cannot say which one is being worked.
    time_frame: str = ""


class SprintListOut(ApiModel):
    items: list[SprintOut] = Field(default_factory=list)
    #: The **one** iteration the team is on, and the same answer WIQL's
    #: ``@currentIteration`` gives — both resolve through the project's default
    #: team. Mark this one as active; a caller that instead badges every item
    #: whose dates contain today is answering a different question.
    current: str = ""


class TicketOut(ApiModel):
    """A work item at the fidelity DAgent renders and prices runs against.

    ``description`` and ``criteria`` are the provider's **own HTML**, not the
    flattened text the hub's ticket store keeps. ``estimateHours`` and
    ``storyPoints`` are nullable and are never defaulted to zero: a zero
    estimate means the team sized it at nothing, which is a different claim from
    having no estimate, and DAgent's dashboard reads the two differently.
    """

    id: str = ""
    title: str = ""
    type: str = ""
    status: str = ""
    assignee: str = ""
    assignee_email: str = ""
    project: str = ""
    area_path: str = ""
    description: str = ""
    criteria: str = ""
    url: str = ""
    estimate_hours: float | None = None
    story_points: float | None = None
    #: The kanban column, which is **not** the state: a board maps several
    #: states onto one column and may add custom ones. Empty for a type that is
    #: not on a board, and the caller then falls back to the state.
    board_column: str = ""


class TicketListOut(ApiModel):
    items: list[TicketOut] = Field(default_factory=list)
    #: The iteration these came from. Echoed because the caller may have omitted
    #: it and let the provider's "current sprint" decide. Empty for the backlog
    #: and board scopes, which span iterations — naming one would be false.
    sprint: str = ""
    #: The provider had more than ``MAX_TICKETS`` to give. Reported rather than
    #: swallowed: a sprint is bounded by its iteration, but a backlog or a board
    #: is not, and a capped list that does not say so reads as a short one.
    truncated: bool = False


class CommentOut(ApiModel):
    author: str = ""
    date: str = ""
    text: str = ""


class CommentListOut(ApiModel):
    items: list[CommentOut] = Field(default_factory=list)
    #: ``False`` when the provider has no comment concept. An empty list then
    #: means "not supported", not "there are none" — the same distinction the
    #: hub's own ticket read-throughs draw.
    supported: bool = True


class StateListOut(ApiModel):
    items: list[str] = Field(default_factory=list)


class StatusOut(ApiModel):
    #: What the provider ended up in, which is not always what was requested.
    status: str = ""


class TransitionIn(ApiModel):
    target_status: str = Field(min_length=1)


class PullRequestOut(ApiModel):
    id: str = ""
    url: str = ""
    title: str = ""
    status: str = ""
    branch: str = ""
    target_branch: str = ""
    author: str = ""
    reviewers: list[str] = Field(default_factory=list)
    created_at: str = ""


class ReviewCommentOut(ApiModel):
    id: str = ""
    thread_id: int | None = None
    author: str = ""
    text: str = ""
    file_path: str = ""
    line: int | None = None
    status: str = "open"
    date: str = ""


class ReviewOut(ApiModel):
    #: ``None`` means no PR is linked to this work item — a real answer, and the
    #: one empty result here that is not a failure.
    pr: PullRequestOut | None = None
    comments: list[ReviewCommentOut] = Field(default_factory=list)
    unresolved_count: int = 0


class CommitOut(ApiModel):
    sha: str = ""
    short_sha: str = ""
    message: str = ""
    author: str = ""
    date: str = ""
    url: str = ""


class CommitListOut(ApiModel):
    items: list[CommitOut] = Field(default_factory=list)


class CommitFileOut(ApiModel):
    path: str = ""
    change_type: str = "modified"
    diff: str = ""
    additions: int = 0
    deletions: int = 0


class CommitFileListOut(ApiModel):
    items: list[CommitFileOut] = Field(default_factory=list)
    #: True when the commit touched more files than one response will carry.
    #: Stated rather than silently truncated — a capped list that does not say so
    #: reads as the whole commit.
    truncated: bool = False


class ReviewSummaryIn(ApiModel):
    #: The work item id, echoed back on the matching entry so the caller does not
    #: have to trust ordering alone.
    ticket_id: str = ""
    #: The PR URL the caller's own run recorded, when it has one. Treated exactly
    #: as ``/pull-request`` treats it: a candidate to verify, never an address to
    #: call.
    pr_url: str = ""


class ReviewSummariesIn(ApiModel):
    items: list[ReviewSummaryIn] = Field(default_factory=list)


class ReviewSummaryOut(ApiModel):
    """One notification's worth of a review — deliberately not a whole review.

    A review bell renders a count and the newest open comment. Sending the thread
    bodies for a board's worth of PRs, which the per-ticket calls this replaces
    did, is most of the payload this endpoint exists to stop sending.
    """

    ticket_id: str = ""
    pr_id: str = ""
    pr_url: str = ""
    pr_title: str = ""
    author: str = ""
    reviewers: list[str] = Field(default_factory=list)
    unresolved_count: int = 0
    latest_author: str = ""
    latest_text: str = ""
    latest_date: str = ""


class ReviewSummaryListOut(ApiModel):
    #: Positional against the request's ``items``. ``None`` means no PR resolved:
    #: nothing linked, or this one item could not be read. An entry with
    #: ``unresolvedCount: 0`` is **not** null — it is "this ticket is on that PR,
    #: and nothing is open on it", which is what lets a caller stop re-resolving
    #: the same work item on every poll.
    #:
    #: A whole batch that could not be read is a 502, never a list of nulls, so an
    #: outage stays distinguishable from an empty board.
    items: list[ReviewSummaryOut | None] = Field(default_factory=list)


class OutcomesIn(ApiModel):
    pr_urls: list[str] = Field(default_factory=list)


class OutcomeOut(ApiModel):
    merged: bool = False
    abandoned: bool = False
    review_comments: int = 0


class OutcomeListOut(ApiModel):
    #: Positional against the request's ``prUrls``; ``None`` where the URL no
    #: longer resolves, so one stale PR cannot blank out a whole funnel.
    items: list[OutcomeOut | None] = Field(default_factory=list)


# ----------------------------------------------------------------- helpers
def _load(db: Session, connection_id: int, principal: User) -> ProviderConnection:
    """Fetch scoped to the caller. Another member's connection 404s, not 403s."""
    return get_owned_or_404(db, ProviderConnection, connection_id, principal)


def _work_item_connection(db: Session, connection_id: int, principal: User) -> ProviderConnection:
    conn = _load(db, connection_id, principal)
    if not conn.advertises(WORK_ITEM):
        raise HTTPException(
            status_code=400,
            detail=f"Connection {conn.id} ({conn.kind}) does not supply 'work_item'",
        )
    return conn


def _run(what: str, conn: ProviderConnection, call):
    """Execute a provider call and map its failure onto a status code.

    The mapping is the contract: a caller must be able to tell "there is nothing
    here" from "we could not find out". Nothing in this module answers 200 with
    an empty body because the provider was unreachable.
    """
    try:
        return call()
    except ProviderUnavailable as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ProviderError as exc:
        # ``ProviderError`` messages are scrubbed of the PAT at the point they
        # are raised; the connection is logged by id and kind only.
        logger.warning("dagent %s unavailable for connection %s (%s)", what, conn.id, conn.kind)
        raise HTTPException(status_code=502, detail=str(exc)) from exc


# ------------------------------------------------------------------ routes
@router.get("/connections", response_model=list[DagentConnectionOut])
def list_connections(
    principal: User = Depends(require_principal),
    db: Session = Depends(get_db),
) -> list[DagentConnectionOut]:
    """Connections DAgent may route through.

    Duplicated from ``GET /connections`` on purpose rather than shared: this
    router is meant to be the single list of what DAgent consumes, and a
    consumer that has to read two routers to find its own surface does not have
    one place to look. The shape is a projection, not a re-export, so a change
    to the hub UI's catalogue cannot silently change DAgent's.
    """
    out = []
    for conn in connection_service.list_connections(db, principal.id):
        config = conn.config or {}
        out.append(
            DagentConnectionOut(
                id=conn.id,
                kind=conn.kind,
                label=conn.label or "",
                base_url=conn.base_url or "",
                project=(config.get("project") or ""),
                capabilities=list(conn.capabilities or []),
                has_pat=bool(conn.pat_encrypted),
            )
        )
    return out


@router.get("/connections/{connection_id}/projects", response_model=list[DagentProjectOut])
def list_projects(
    connection_id: int,
    principal: User = Depends(require_principal),
    db: Session = Depends(get_db),
) -> list[DagentProjectOut]:
    """Projects under the connection's organisation.

    Unlike the hub UI's equivalent this does **not** degrade to an empty list on
    an upstream failure. DAgent's project picker being empty is indistinguishable
    from an organisation with no projects, and it is the screen a user lands on
    first — so a failure has to say so.
    """
    conn = _work_item_connection(db, connection_id, principal)
    adapter = connection_service.adapter_for(conn)
    rows = _run("projects", conn, adapter.list_projects)
    return [
        DagentProjectOut(
            id=str(r.get("id") or r.get("name") or ""),
            name=r.get("name", ""),
            description=r.get("description", "") or "",
        )
        for r in rows
    ]


@router.get("/connections/{connection_id}/sprints", response_model=SprintListOut)
def list_sprints(
    connection_id: int,
    project: str | None = Query(None),
    principal: User = Depends(require_principal),
    db: Session = Depends(get_db),
) -> SprintListOut:
    """The team's iterations, newest first, with which one is current.

    ``project`` is the same selector ``/tickets`` takes, and for the same
    reason: DAgent picks a project in its header while one connection spans a
    whole organisation. Served from ``dagent_provider`` rather than the shared
    adapter, whose ``list_sprints`` reads the project off the connection and so
    cannot answer for the one the caller actually has open.

    Scoped to the project's **default team**, because that is the only scope a
    sprint list has in ADO — its own URL is ``_sprints/backlog/<team>/…``. The
    project's whole iteration tree is a different thing entirely: every team's
    sprints at once, which matches no screen a user has ever seen.
    """
    conn = _work_item_connection(db, connection_id, principal)
    rows = _run("sprints", conn, lambda: dagent_provider.list_sprints(conn, project=project))

    items = [
        SprintOut(
            id=str(r.get("id", "")),
            name=r.get("name", ""),
            path=r.get("path", "") or r.get("name", ""),
            start_date=r.get("start_date") or "",
            finish_date=r.get("finish_date") or "",
            # ADO's own classification, not a comparison of two dates against
            # today. It is scoped to the team whose iterations these are, so
            # exactly one is "current" — which is the whole reason this is read
            # from team settings rather than the project's iteration tree.
            time_frame=r.get("time_frame") or "",
        )
        for r in rows
    ]
    items.sort(key=lambda s: s.start_date, reverse=True)
    current = next((s.name for s in items if s.time_frame == "current"), "")
    return SprintListOut(items=items, current=current)


@router.get("/connections/{connection_id}/tickets", response_model=TicketListOut)
def list_tickets(
    connection_id: int,
    project: str | None = Query(None),
    sprint: str | None = Query(None),
    scope: str = Query("sprint", pattern="^(sprint|backlog|board)$"),
    principal: User = Depends(require_principal),
    db: Session = Depends(get_db),
) -> TicketListOut:
    """A view's work items, read **live from the provider**.

    Deliberately not served from the hub's ``tickets`` table. That table is a
    normalised mirror built for QAgent's needs: it flattens the description to
    plain text and stores no deep link, no original estimate and no story
    points. DAgent renders the rich text and prices its runs against the
    estimate, so reading through the store would lose both without saying so.

    ``scope`` picks which of three views to build — ``sprint`` (the iteration
    named, or the team's current one when ``sprint`` is omitted), ``backlog``
    (open work not scheduled into any iteration) or ``board`` (every open work
    item, with its kanban column). The three are separate provider queries, not
    filters over one list; see ``dagent_provider._wiql``. Rejected at the edge
    by ``pattern`` rather than defaulted, because silently treating a
    misspelled scope as "sprint" would answer a question nobody asked.
    """
    conn = _work_item_connection(db, connection_id, principal)
    tickets, label, truncated = _run(
        "tickets",
        conn,
        lambda: dagent_provider.list_tickets(conn, project=project, sprint=sprint, scope=scope),
    )
    return TicketListOut(
        items=[TicketOut.model_validate(t) for t in tickets],
        sprint=label,
        truncated=truncated,
    )


@router.get("/connections/{connection_id}/tickets/{external_id}/comments", response_model=CommentListOut)
def list_ticket_comments(
    connection_id: int,
    external_id: str,
    principal: User = Depends(require_principal),
    db: Session = Depends(get_db),
) -> CommentListOut:
    """The work item's discussion thread, read live through the hub's PAT."""
    conn = _work_item_connection(db, connection_id, principal)
    adapter = connection_service.adapter_for(conn)
    if not getattr(adapter, "supports_comments", False):
        return CommentListOut(items=[], supported=False)
    rows = _run("comments", conn, lambda: adapter.fetch_comments(external_id))
    return CommentListOut(
        items=[
            CommentOut(
                author=r.get("who") or r.get("author") or "",
                date=r.get("when") or r.get("date") or "",
                text=r.get("text") or "",
            )
            for r in rows
        ]
    )


@router.get("/connections/{connection_id}/tickets/{external_id}/states", response_model=StateListOut)
def list_ticket_states(
    connection_id: int,
    external_id: str,
    work_item_type: str = Query(..., alias="workItemType"),
    project: str | None = Query(None),
    principal: User = Depends(require_principal),
    db: Session = Depends(get_db),
) -> StateListOut:
    """States **this work item type** may hold.

    Scoped to the type, not the union across the project. A dropdown built from
    the union offers transitions the provider rejects outright: ADO process
    templates differ, so "Done" simply does not exist on an Agile User Story.

    ``external_id`` is in the path for a consistent shape and to keep the route
    unambiguous; the type is what actually decides the answer.
    """
    conn = _work_item_connection(db, connection_id, principal)
    items = _run(
        "work-item states",
        conn,
        lambda: dagent_provider.work_item_states(conn, work_item_type, project=project),
    )
    return StateListOut(items=items)


@router.get("/connections/{connection_id}/tickets/{external_id}/status", response_model=StatusOut)
def read_ticket_status(
    connection_id: int,
    external_id: str,
    principal: User = Depends(require_principal),
    db: Session = Depends(get_db),
) -> StatusOut:
    """The work item's current state at the provider.

    DAgent reads this back after a write, and after a *failed* write, so what it
    displays is the provider's state rather than an optimistic local guess that
    quietly drifted.
    """
    conn = _work_item_connection(db, connection_id, principal)
    status = _run("ticket status", conn, lambda: dagent_provider.ticket_status(conn, external_id))
    return StatusOut(status=status)


@router.post("/connections/{connection_id}/tickets/{external_id}/status", response_model=StatusOut)
def transition_ticket(
    connection_id: int,
    external_id: str,
    payload: TransitionIn,
    principal: User = Depends(require_principal),
    db: Session = Depends(get_db),
) -> StatusOut:
    """Transition the work item.

    Delegates to the existing adapter's ``update_status``, which already resolves
    the requested label against the type's real configured states before writing
    — the behaviour that makes "Code Review" work on a process template that
    calls it something else. A rejected transition surfaces as 502 carrying the
    provider's own reason, because that reason is the only actionable part.
    """
    conn = _work_item_connection(db, connection_id, principal)
    adapter = connection_service.adapter_for(conn)
    _run("transition", conn, lambda: adapter.update_status(external_id, payload.target_status))
    return StatusOut(status=payload.target_status)


# ------------------------------------------------------------ pull requests
@router.get("/connections/{connection_id}/pull-request", response_model=ReviewOut)
def pull_request_review(
    connection_id: int,
    ticket_id: str | None = Query(None, alias="ticketId"),
    pr_url: str | None = Query(None, alias="prUrl"),
    principal: User = Depends(require_principal),
    db: Session = Depends(get_db),
) -> ReviewOut:
    """The PR linked to a work item, and its review threads.

    Both selectors are optional and both are used. ``ticketId`` resolves through
    the work item's ArtifactLink, which only exists when the PR was explicitly
    linked; ``prUrl`` is the URL DAgent's own run recorded, which is the case an
    agent-opened PR usually falls into. Each candidate is verified against the
    repositories API before use, so a stale artifact link falls through to the
    recorded URL rather than 404ing the whole tab.

    ``pr: null`` means nothing is linked. That is a real answer, not a failure.
    """
    conn = _work_item_connection(db, connection_id, principal)
    data = _run(
        "pull-request review",
        conn,
        lambda: dagent_provider.pull_request_review(conn, ticket_id=ticket_id, pr_url=pr_url),
    )
    return ReviewOut.model_validate(data)


@router.post("/connections/{connection_id}/pull-request/review-summaries", response_model=ReviewSummaryListOut)
def pull_request_review_summaries(
    connection_id: int,
    payload: ReviewSummariesIn,
    principal: User = Depends(require_principal),
    db: Session = Depends(get_db),
) -> ReviewSummaryListOut:
    """Unresolved-review-comment summaries for many work items, in one request.

    POST rather than GET for the same reason as ``/outcomes``: the list is a
    board's worth of tickets and does not fit a query string reliably.

    This is the batch form of ``GET /pull-request``. DAgent's bell polls the
    whole board on a timer, and asking per ticket meant one round-trip and one
    full review payload per ticket per poll. The answer here is positional and
    carries only the count and the newest open comment.

    Neither selector becomes an upstream address: ``prUrl`` is parsed for a
    repository and PR id and then verified against this connection's own base
    URL, exactly as the single-ticket route does.
    """
    conn = _work_item_connection(db, connection_id, principal)
    rows = _run(
        "review summaries",
        conn,
        lambda: dagent_provider.review_summaries(
            conn,
            [{"ticketId": item.ticket_id, "prUrl": item.pr_url} for item in payload.items],
        ),
    )
    return ReviewSummaryListOut(
        items=[None if r is None else ReviewSummaryOut.model_validate(r) for r in rows]
    )


@router.get("/connections/{connection_id}/pull-request/commits", response_model=CommitListOut)
def pull_request_commits(
    connection_id: int,
    ticket_id: str | None = Query(None, alias="ticketId"),
    pr_url: str | None = Query(None, alias="prUrl"),
    principal: User = Depends(require_principal),
    db: Session = Depends(get_db),
) -> CommitListOut:
    """Every commit on the PR's source branch, newest first."""
    conn = _work_item_connection(db, connection_id, principal)
    rows = _run(
        "pull-request commits",
        conn,
        lambda: dagent_provider.pull_request_commits(conn, ticket_id=ticket_id, pr_url=pr_url),
    )
    return CommitListOut(items=[CommitOut.model_validate(r) for r in rows])


@router.get("/connections/{connection_id}/pull-request/commits/{sha}", response_model=CommitFileListOut)
def pull_request_commit_files(
    connection_id: int,
    sha: str,
    ticket_id: str | None = Query(None, alias="ticketId"),
    pr_url: str | None = Query(None, alias="prUrl"),
    principal: User = Depends(require_principal),
    db: Session = Depends(get_db),
) -> CommitFileListOut:
    """One commit's file changes, each with a unified diff.

    Azure DevOps has no "give me the patch" endpoint, so each diff is built from
    the file's content at this commit and at its first parent — two reads per
    file, which is why the count is capped and the cap is reported.
    """
    conn = _work_item_connection(db, connection_id, principal)
    rows = _run(
        "commit files",
        conn,
        lambda: dagent_provider.commit_files(conn, sha, ticket_id=ticket_id, pr_url=pr_url),
    )
    return CommitFileListOut(
        items=[CommitFileOut.model_validate(r) for r in rows],
        truncated=len(rows) >= dagent_provider.MAX_COMMIT_FILES,
    )


@router.post("/connections/{connection_id}/pull-request/outcomes", response_model=OutcomeListOut)
def pull_request_outcomes(
    connection_id: int,
    payload: OutcomesIn,
    principal: User = Depends(require_principal),
    db: Session = Depends(get_db),
) -> OutcomeListOut:
    """What became of a batch of PRs — DAgent's delivery funnel.

    POST rather than GET because the list is long: a dashboard sends dozens of
    URLs, which do not fit a query string reliably.

    **The URLs are parsed, not followed.** A repository name and a PR id are
    taken out of each one and the request is then built from the connection's own
    base URL. Nothing the caller sends becomes an upstream address, which is what
    keeps this from being the caller-directed forwarder INTEGRATION.md §4 rules
    out.

    Answers positionally, with a null where a URL no longer resolves.
    """
    conn = _work_item_connection(db, connection_id, principal)
    rows = _run(
        "pull-request outcomes",
        conn,
        lambda: dagent_provider.pull_request_outcomes(conn, payload.pr_urls),
    )
    return OutcomeListOut(
        items=[None if r is None else OutcomeOut.model_validate(r) for r in rows]
    )
