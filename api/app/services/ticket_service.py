"""Ticket store — listing, lookup, upsert-on-resync, delete, and the sync seam.

The read side (INTEGRATION.md §3) is complete and self-contained: it only needs
the ``tickets`` table and ``app.services.ownership``.

## The sync seam

Sync needs a **provider adapter**, and adapters live in ``app.services.adapters``
— a module owned by the connections slice, which is being built in parallel and
does not exist here yet. Rather than block on it (or, worse, fork a second copy
of it), this module declares the *narrowest* interface sync actually needs:

* :class:`TicketSource` — one method, :meth:`TicketSource.fetch_tickets`, whose
  signature and return shape are deliberately those of
  ``adapters.base.ProviderAdapter.fetch_tickets`` / ``NormalizedTicket``, so the
  real adapter satisfies this protocol *as written*, with no shim;
* :class:`ResolvedSource` — the source plus the two stamps sync writes onto every
  row (``provider_kind`` and the originating ``connection_id``);
* :func:`resolve_source` — an injectable provider function, resolved **lazily at
  call time**, that defaults to :func:`_resolve_from_adapters`.

:func:`_resolve_from_adapters` imports ``app.services.adapters`` /
``app.services.connection_service`` *inside the function body*. Until those
exist the import fails and sync raises :class:`TicketSyncUnavailable` (a 503 —
"not wired yet", never a silent success). Wiring the real thing up is then a
matter of that one function resolving, not of changing any caller.

Tests inject a fake through :func:`use_ticket_source_resolver`.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

from sqlalchemy import String, and_, cast, or_
from sqlalchemy.orm import Query, Session

from app.db import utcnow
from app.models.ticket import Ticket
from app.models.user import User
from app.services import ticket_query
from app.services.ownership import owned, stamp_owner

# --------------------------------------------------------------------- seam

#: A provider-agnostic ticket, exactly the shape of
#: ``app.services.adapters.base.NormalizedTicket``. Keys (all optional except
#: ``external_id``): external_id, provider_kind, title, work_item_type, status,
#: priority, assignee, sprint, area_path, epic, description, labels(list[str]),
#: acceptance_criteria(list[str]), acceptance_criteria_html(str),
#: comments(list[dict]), attachments(list[dict]), linked_prs(list[dict]).
#: ``note`` may be present and is ignored — the hub does not store QA notes.
NormalizedTicket = dict[str, Any]


class TicketSyncUnavailable(RuntimeError):
    """No provider adapter layer is available to sync from (503, not 200)."""


class TicketSourceError(RuntimeError):
    """The source was reached but the upstream provider call failed (502).

    The adapter layer's ``ProviderError`` is a ``RuntimeError`` too; the default
    resolver re-raises it as this type so callers never import from the adapters
    package.
    """


@runtime_checkable
class TicketSource(Protocol):
    """The one capability ticket sync needs from a provider adapter.

    Structurally identical to ``ProviderAdapter.fetch_tickets``, so an adapter
    instance *is* a ``TicketSource`` without adaptation.
    """

    def fetch_tickets(
        self,
        *,
        mode: str = "sprint",
        sprint: str | None = None,
        sprint_path: str | None = None,
        area_path: str | None = None,
        states: list[str] | None = None,
        work_item_types: list[str] | None = None,
        ticket_ids: list[str] | None = None,
        include_comments: bool = False,
        project: str | None = None,
    ) -> list[NormalizedTicket]:
        """Fetch and normalise work items for the given selection."""
        ...


@dataclass(frozen=True)
class ResolvedSource:
    """A :class:`TicketSource` plus the origin stamps sync writes onto each row."""

    source: TicketSource
    provider_kind: str
    connection_id: int | None = None
    #: Human label for the audit trail (connection name, or the kind).
    label: str = ""


#: ``(db, user, connection_id, provider_kind) -> ResolvedSource``.
TicketSourceResolver = Callable[[Session, User | None, int | None, str | None], ResolvedSource]


def _resolve_from_adapters(
    db: Session,
    user: User | None,
    connection_id: int | None,
    provider_kind: str | None,
) -> ResolvedSource:
    """Default resolver — the connections slice's adapters, if they are here.

    Imported inside the function so this module has no import-time dependency on
    a package that may not exist yet. When it lands, this is the only place that
    needs to know its API.
    """
    try:
        # `adapters` is imported purely as a presence check: it is the package
        # this seam exists to defer, and connection_service is how one is picked.
        from app.services import adapters, connection_service  # noqa: F401
    except ImportError as exc:  # pragma: no cover - exercised once #32 lands
        raise TicketSyncUnavailable(
            "Ticket sync needs the provider connections layer, which is not "
            "available in this deployment yet."
        ) from exc

    # Wired to the connections slice. Its visibility argument is `viewer_id`
    # (own + shared), and `adapter_for` takes the connection alone — it is the
    # single PAT decryption site and needs no session.
    viewer_id = user.id if user else None
    connection = connection_service.get_connection(db, connection_id, viewer_id)
    if connection is None and provider_kind:
        connection = connection_service.first_of_kind(db, provider_kind, viewer_id)
    if connection is None:
        raise LookupError(
            f"No work-item connection is configured for '{provider_kind or connection_id}'"
        )
    try:
        adapter = connection_service.adapter_for(connection)
    except Exception as exc:
        raise TicketSourceError(str(exc)) from exc
    return ResolvedSource(
        source=adapter,
        provider_kind=connection.kind,
        connection_id=connection.id,
        label=connection.label or connection.kind,
    )


#: Swapped by :func:`use_ticket_source_resolver`; read at call time, never bound
#: into a default argument, so injection works after import.
_resolver: TicketSourceResolver = _resolve_from_adapters


def resolve_source(
    db: Session,
    user: User | None,
    connection_id: int | None,
    provider_kind: str | None,
) -> ResolvedSource:
    return _resolver(db, user, connection_id, provider_kind)


def set_ticket_source_resolver(resolver: TicketSourceResolver | None) -> TicketSourceResolver:
    """Replace the resolver; ``None`` restores the default. Returns the previous."""
    global _resolver
    previous = _resolver
    _resolver = resolver or _resolve_from_adapters
    return previous


@contextmanager
def use_ticket_source_resolver(resolver: TicketSourceResolver) -> Iterator[None]:
    """Scoped injection, for tests: ``with use_ticket_source_resolver(fake): ...``."""
    previous = set_ticket_source_resolver(resolver)
    try:
        yield
    finally:
        set_ticket_source_resolver(previous)


# --------------------------------------------------------------------- reads
def _visible(db: Session, user: User | None) -> Query[Ticket]:
    """Every read starts here: own rows plus the shared namespace, nothing else."""
    return owned(db.query(Ticket), Ticket, user)


# ───────────────────────────────────────────── the mirror query compiler
#
# The ``mirror`` destination of :mod:`app.services.ticket_query`: a TicketQuery
# compiled onto our own columns. Parameterised SQLAlchemy throughout, so unlike the
# WIQL and JQL compilers this one has no string-escaping surface at all — which is
# why it is the destination the query builder is built against first.

#: Which column each clause field reads. A field absent here must also be absent
#: from the mirror's entry in ``ticket_query.CAPABILITIES``; a test pins that, or
#: the matrix would offer a field this compiler silently ignores.
_QUERY_COLUMNS: dict[str, Any] = {
    "workItemType": Ticket.work_item_type,
    "state": Ticket.status,
    "assignee": Ticket.assignee,
    "areaPath": Ticket.area_path,
    "iterationPath": Ticket.sprint,
    "tags": Ticket.labels,
    "title": Ticket.title,
    "changedSince": Ticket.synced_at,
    "createdSince": Ticket.synced_at,
    "priority": Ticket.priority,
    "epic": Ticket.epic,
}


def _clause_condition(clause: ticket_query.QueryClause) -> Any | None:
    """One clause as a SQLAlchemy expression, or ``None`` when it says nothing."""
    column = _QUERY_COLUMNS.get(clause.field)
    values = clause.filled
    if column is None or not values:
        return None
    first = values[0]
    # `tags` is a JSON list here rather than ADO's semicolon-joined string, so a
    # substring match has to run against its text form.
    text = cast(column, String) if clause.field == "tags" else column

    if clause.operator == "is":
        return column == first
    if clause.operator == "isNot":
        return column != first
    if clause.operator == "in":
        return column.in_(values)
    if clause.operator == "notIn":
        return column.notin_(values)
    if clause.operator == "contains":
        return text.ilike(f"%{first}%")
    if clause.operator == "notContains":
        return ~text.ilike(f"%{first}%")
    if clause.operator == "under":
        # UNDER semantics, with the same guard as the `area_path` kwarg below:
        # startswith with autoescape, never a raw LIKE, because ADO paths contain
        # backslashes and Postgres reads a backslash as LIKE's escape character.
        return column.startswith(first, autoescape=True)
    if clause.operator == "onOrAfter":
        return column >= first
    if clause.operator == "onOrBefore":
        return column <= first
    return None


def apply_query(query: Query[Ticket], spec: ticket_query.TicketQuery) -> Query[Ticket]:
    """Narrow ``query`` by ``spec``. Callers validate first; this only compiles.

    ``match: "any"`` ORs the clauses, but as a **single** filter on top of whatever
    scoping the caller already applied — so an OR can widen the result within what
    the user may see and never past it.
    """
    conditions = [
        condition
        for condition in (_clause_condition(clause) for clause in spec.effective_clauses)
        if condition is not None
    ]
    if not conditions:
        return query
    return query.filter(or_(*conditions) if spec.match == "any" else and_(*conditions))


def list_tickets(
    db: Session,
    user: User | None,
    *,
    project_id: int | None = None,
    provider_kind: str | None = None,
    connection_id: int | None = None,
    status: str | None = None,
    assignee: str | None = None,
    sprint: str | None = None,
    area_path: str | None = None,
    states: list[str] | None = None,
    work_item_types: list[str] | None = None,
    priority: str | None = None,
    epic: str | None = None,
    q: str | None = None,
    spec: ticket_query.TicketQuery | None = None,
    page: int = 1,
    page_size: int = 25,
) -> tuple[list[Ticket], int]:
    """One page of tickets visible to ``user``, plus the unpaged total.

    ``spec`` is the clause-based query (the ``mirror`` destination). It composes
    with the individual kwargs rather than replacing them: the kwargs are the
    existing pill filters and the `GET /tickets` contract that agents already call,
    and both narrow the same visible set. Callers validate ``spec`` first.
    """
    query = _visible(db, user)
    if spec is not None:
        query = apply_query(query, spec)
    if project_id is not None:
        query = query.filter(Ticket.project_id == project_id)
    if provider_kind:
        query = query.filter(Ticket.provider_kind == provider_kind)
    if connection_id is not None:
        query = query.filter(Ticket.connection_id == connection_id)
    if status:
        query = query.filter(Ticket.status == status)
    if assignee:
        query = query.filter(Ticket.assignee == assignee)
    if sprint:
        query = query.filter(Ticket.sprint == sprint)
    if area_path:
        # UNDER semantics — the selected path and its children. startswith with
        # autoescape=True, never a raw LIKE: ADO area paths contain backslashes
        # ("Surency\\Data Platform") and Postgres treats backslash as LIKE's
        # default escape character, so a raw pattern would match nothing.
        query = query.filter(Ticket.area_path.startswith(area_path, autoescape=True))
    if states:
        query = query.filter(Ticket.status.in_(states))
    if work_item_types:
        query = query.filter(Ticket.work_item_type.in_(work_item_types))
    if priority:
        query = query.filter(Ticket.priority == priority)
    if epic:
        query = query.filter(Ticket.epic == epic)
    if q:
        like = f"%{q}%"
        query = query.filter(Ticket.title.ilike(like) | Ticket.external_id.ilike(like))

    total = query.count()
    page = max(page, 1)
    page_size = max(1, min(page_size, 200))
    items = (
        query.order_by(Ticket.synced_at.desc().nullslast(), Ticket.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return items, total


def get_ticket(
    db: Session,
    user: User | None,
    external_id: str,
    *,
    provider_kind: str | None = None,
) -> Ticket | None:
    """One ticket by its provider id, scoped to ``user``.

    A ticket owned by *another* user is indistinguishable from one that does not
    exist — the caller turns ``None`` into a 404, never a 403.
    """
    query = _visible(db, user).filter(Ticket.external_id == external_id)
    if provider_kind:
        query = query.filter(Ticket.provider_kind == provider_kind)
    return query.order_by(Ticket.id.desc()).first()


# -------------------------------------------------------------------- writes
#: Columns filled from a NormalizedTicket, with the fallback used when the
#: provider omits the key. Keeping this as data (rather than 15 assignments)
#: means a new normalised field is one line here and one column in a migration.
_SYNCED_FIELDS: tuple[tuple[str, Any], ...] = (
    ("title", ""),
    ("work_item_type", "User Story"),
    ("status", ""),
    ("priority", "Medium"),
    ("assignee", ""),
    ("sprint", ""),
    ("area_path", ""),
    ("epic", ""),
    ("description", ""),
    ("acceptance_criteria_html", ""),
)
_SYNCED_LIST_FIELDS = (
    "labels",
    "acceptance_criteria",
    "comments",
    "attachments",
    "linked_prs",
)


def upsert_ticket(
    db: Session,
    user: User | None,
    item: NormalizedTicket,
    *,
    provider_kind: str,
    connection_id: int | None = None,
    project_id: int | None = None,
) -> Ticket | None:
    """Insert or update one normalised ticket. Does **not** commit.

    Identity is ``(owner scope, provider_kind, external_id)`` — a re-sync of the
    same work item updates the row in place rather than creating a duplicate.
    Returns ``None`` when the item carries no ``external_id`` (nothing to key on).
    """
    external_id = str(item.get("external_id") or "").strip()
    if not external_id:
        return None

    ticket = (
        _visible(db, user)
        .filter(Ticket.external_id == external_id, Ticket.provider_kind == provider_kind)
        .first()
    )
    if ticket is None:
        ticket = stamp_owner(Ticket(external_id=external_id, provider_kind=provider_kind), user)
        db.add(ticket)

    if connection_id is not None:
        ticket.connection_id = connection_id
    if project_id is not None:
        ticket.project_id = project_id

    for field, fallback in _SYNCED_FIELDS:
        value = item.get(field)
        setattr(ticket, field, fallback if value is None else value)
    for field in _SYNCED_LIST_FIELDS:
        value = item.get(field)
        setattr(ticket, field, list(value) if value else [])

    ticket.synced_at = utcnow()
    return ticket


def preview_tickets(
    db: Session,
    user: User | None,
    *,
    connection_id: int | None = None,
    provider_kind: str | None = None,
    spec: ticket_query.TicketQuery | None = None,
    project: str | None = None,
    limit: int = 10,
) -> tuple[int, list[Any], ResolvedSource]:
    """Run a query against the provider and return what it *would* import.

    Nothing is written. This is what makes an honest count possible before a pull:
    the handoff's "~24 items" hints were deleted precisely because nothing could
    count a provider-side scope without performing it (`components/import/
    scopes.ts`). Now something can.

    Returns the total the provider matched, a short sample, and the resolved
    source. The sample is capped because a preview is for confirming the shape of
    the result, not for reading it.
    """
    resolved = resolve_source(db, user, connection_id, provider_kind)
    try:
        # Counted separately from the sample: `fetch_tickets` is capped so a bulk
        # sync cannot hang, and a capped number is the wrong answer to "how many
        # are there" — it reads as the truth. `count_tickets` is uncapped where the
        # provider can do it cheaply.
        total = resolved.source.count_tickets(spec=spec, project=project)
        fetched = resolved.source.fetch_tickets(
            include_comments=False,
            project=project,
            spec=spec,
        )
    except (TicketSourceError, TicketSyncUnavailable):
        raise
    except Exception as exc:
        raise TicketSourceError(str(exc)) from exc

    return total, list(fetched or [])[:limit], resolved


def sync_tickets(
    db: Session,
    user: User | None,
    *,
    connection_id: int | None = None,
    provider_kind: str | None = None,
    mode: str = "sprint",
    sprint: str | None = None,
    sprint_path: str | None = None,
    area_path: str | None = None,
    states: list[str] | None = None,
    work_item_types: list[str] | None = None,
    ticket_ids: list[str] | None = None,
    project: str | None = None,
    project_id: int | None = None,
    spec: ticket_query.TicketQuery | None = None,
) -> tuple[list[Ticket], ResolvedSource]:
    """Pull from the resolved :class:`TicketSource` and upsert every row.

    Both the source and the rows are scoped to ``user``: a member syncs via, and
    into, their own data. Raises :class:`TicketSyncUnavailable` (no adapter
    layer), :class:`LookupError` (no such connection) or
    :class:`TicketSourceError` (the provider call failed) — the router maps each
    to its status code.
    """
    resolved = resolve_source(db, user, connection_id, provider_kind)
    try:
        fetched = resolved.source.fetch_tickets(
            mode=mode,
            sprint=sprint,
            sprint_path=sprint_path,
            area_path=area_path,
            states=states,
            work_item_types=work_item_types,
            ticket_ids=ticket_ids,
            # Comments are one extra provider request per ticket — an N+1 that
            # makes a bulk sync crawl. They are loaded on demand instead.
            include_comments=False,
            project=project,
            spec=spec,
        )
    except (TicketSourceError, TicketSyncUnavailable):
        raise
    except Exception as exc:
        raise TicketSourceError(str(exc)) from exc

    synced: list[Ticket] = []
    for item in fetched or []:
        ticket = upsert_ticket(
            db,
            user,
            item,
            provider_kind=resolved.provider_kind,
            connection_id=resolved.connection_id,
            project_id=project_id,
        )
        if ticket is not None:
            synced.append(ticket)
    db.commit()
    for ticket in synced:
        db.refresh(ticket)
    return synced, resolved


def delete_ticket(db: Session, user: User | None, external_id: str) -> bool:
    """Local-delete one ticket. Never calls the provider — a re-sync restores it.

    Returns False when nothing visible to ``user`` matches.
    """
    ticket = get_ticket(db, user, external_id)
    if ticket is None:
        return False
    db.delete(ticket)
    db.commit()
    return True
