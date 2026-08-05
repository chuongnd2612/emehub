"""Provider passthrough for one ticket — the hub makes the call, the PAT stays here.

INTEGRATION.md §3/§4. An agent needs to read a work item's comments and its
provider-side test cases, and to write back to the provider — post a results
comment, transition the work item, create test cases — all without holding a
provider credential. So the hub does what ``POST /tickets/sync`` already does for
work items: resolve the ticket's own connection, decrypt its own PAT, call the
provider.

Reads are ``list_comments`` / ``list_test_cases``; writes are ``publish_comment``,
``transition`` and ``create_test_cases``. The writes are what let an agent stop
storing provider credentials at all — they are the provider side of QAgent's
Publish and Link screens.

**The caller names a ticket, never an upstream.** That is the property that keeps
this off the SSRF surface which deferred the generic
``POST /connections/{id}/proxy``: there is no caller-supplied URL, host, header or
method anywhere in this module. The connection comes from the ticket row via
``connection_service.resolve_work_item_for_ticket``, which additionally refuses a
connection that does not *advertise* ``work_item``.

## Three outcomes, deliberately distinguished

An empty list is the wrong answer to two of the three things that can happen, and
conflating them is exactly the bug QAgent shipped twice (q-agent#490, #491:
"stop reporting a failed load as 'no data'"). So:

* **the provider has no such concept** — Jira has no test cases, GitHub issues
  have none either. That is a fact about the ticket, not a failure: ``supported``
  comes back ``False`` with an empty list and a ``200``.
* **the call failed** — :class:`ProviderUnavailable`, mapped to ``502``. Never an
  empty list. The adapters were changed alongside this module so their public
  read methods raise instead of swallowing; the sync path still swallows, because
  a comment failure must not fail a whole sync.
* **there are genuinely none** — ``supported`` is ``True`` and the list is empty.

## Writes keep the hub's own row honest

A comment the hub published and a transition it applied are both changes the hub
made itself. Leaving them to be discovered by the next sync would mean
``GET /tickets/{id}`` serving a status the hub knows is wrong, so both mirror into
the ticket row — and the transition mirrors **only** after the provider call
returns without raising.

## The seam

``ticket_service`` defers its adapter dependency through an injectable resolver
so the store can be tested without the connections layer existing. This module
does the same, for the same reason and with the same shape — see
:func:`use_adapter_resolver`.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from typing import Any, NamedTuple, Protocol, runtime_checkable

from sqlalchemy.orm import Session

__all__ = [
    "AdapterLayerMissing",
    "AdapterResolver",
    "CaseRequest",
    "CaseResult",
    "NoWorkItemConnection",
    "ProviderRead",
    "ProviderUnavailable",
    "TicketAdapter",
    "create_test_cases",
    "list_comments",
    "list_test_cases",
    "publish_comment",
    "resolve_adapter",
    "set_adapter_resolver",
    "transition",
    "use_adapter_resolver",
]


class ProviderRead(NamedTuple):
    """The result of one provider read.

    ``supported`` and ``project_wide`` are why this is not a bare list: the
    caller has to be able to say *why* a list is empty, and whether it is
    scoped to the ticket it asked about.
    """

    items: list[dict[str, Any]]
    #: The provider implements this read at all.
    supported: bool
    #: The provider answered for the whole project, not just this ticket.
    project_wide: bool = False


class ProviderUnavailable(RuntimeError):
    """The provider call could not be completed. Maps to ``502``.

    Deliberately distinct from "there are none": a caller must be able to tell a
    failed read from an empty one.
    """


class NoWorkItemConnection(LookupError):
    """No work-item-capable connection routes this ticket. Maps to ``404``.

    A ``LookupError`` because from the caller's side it is indistinguishable
    from — and as unactionable as — the ticket not being there.
    """


class AdapterLayerMissing(RuntimeError):
    """The provider-adapter package is not present in this deployment (``503``)."""


@runtime_checkable
class TicketAdapter(Protocol):
    """What this module needs from a provider adapter.

    Structural, and a strict subset of ``adapters.base.ProviderAdapter``, so the
    real adapter satisfies it as written and a test fake stays small.
    """

    supports_comments: bool
    supports_test_cases: bool
    test_cases_project_wide: bool

    def fetch_comments(self, ticket_external_id: str) -> list[dict[str, Any]]: ...

    def list_test_cases(
        self, ticket_external_id: str | None = None
    ) -> list[dict[str, Any]]: ...

    def publish_comment(
        self,
        ticket_external_id: str,
        body: str,
        *,
        attachments: list[str] | None = None,
    ) -> str: ...

    def update_status(self, ticket_external_id: str, target_status: str) -> None: ...

    def create_test_case(
        self,
        ticket_external_id: str,
        *,
        title: str,
        precondition: str = "",
        steps: list[dict[str, Any]] | None = None,
        priority: str = "Medium",
        link: bool = True,
    ) -> dict[str, Any]: ...


class CaseRequest(NamedTuple):
    """One test case to create."""

    title: str
    precondition: str = ""
    steps: list[dict[str, Any]] = []  # noqa: RUF012 - NamedTuple defaults are read-only
    priority: str = "Medium"


class CaseResult(NamedTuple):
    """The outcome of one case in a batch.

    Per-case rather than per-request because partial success is the normal case,
    not an edge case: QAgent's Link screen creates every case for a ticket in one
    pass and must report which ones landed.
    """

    title: str
    external_id: str = ""
    url: str = ""
    status: str = ""
    linked: bool = False
    error: str = ""


#: ``(db, ticket) -> TicketAdapter``.
AdapterResolver = Callable[[Session, Any], TicketAdapter]


def _resolve_from_connections(db: Session, ticket: Any) -> TicketAdapter:
    """Default resolver — the ticket's own connection, through the adapters.

    Imported inside the function so this module has no import-time dependency on
    a package that may be absent, matching ``ticket_service``.
    """
    try:
        from app.services import connection_service
        from app.services.adapters.base import ProviderError
    except ImportError as exc:  # pragma: no cover - defensive, mirrors ticket_service
        raise AdapterLayerMissing(
            "Provider reads need the connections layer, which is not available "
            "in this deployment."
        ) from exc

    try:
        connection = connection_service.resolve_work_item_for_ticket(db, ticket)
    except ProviderError as exc:
        # "No work-item connection is configured for '<kind>'" — a routing gap,
        # not a provider failure, so it must not read as a 502.
        raise NoWorkItemConnection(str(exc)) from exc
    try:
        return connection_service.adapter_for(connection)
    except ProviderError as exc:
        # Undecryptable PAT under the current key. "Unavailable", never an empty
        # credential passed on — that would read as "no PAT configured".
        raise ProviderUnavailable(str(exc)) from exc


_resolver: AdapterResolver = _resolve_from_connections


def set_adapter_resolver(resolver: AdapterResolver | None) -> AdapterResolver:
    """Swap the resolver. Returns the previous one."""
    global _resolver
    previous = _resolver
    _resolver = resolver or _resolve_from_connections
    return previous


@contextmanager
def use_adapter_resolver(resolver: AdapterResolver) -> Iterator[None]:
    """Scope a resolver to a block, restoring the previous one on exit."""
    previous = set_adapter_resolver(resolver)
    try:
        yield
    finally:
        set_adapter_resolver(previous)


def resolve_adapter(db: Session, ticket: Any) -> TicketAdapter:
    """The adapter this ticket's provider work routes through.

    Read through the module global at call time, never bound into a default
    argument, so injection works after import.
    """
    return _resolver(db, ticket)


def _read(
    db: Session,
    ticket: Any,
    *,
    capability: str,
    call: Callable[[TicketAdapter], list[dict[str, Any]]],
    what: str,
    project_wide_attr: str | None = None,
) -> ProviderRead:
    """Resolve, check the capability, call."""
    adapter = resolve_adapter(db, ticket)
    if not getattr(adapter, capability, False):
        return ProviderRead([], False)
    try:
        items = call(adapter)
    except (ProviderUnavailable, AdapterLayerMissing, NoWorkItemConnection):
        raise
    except Exception as exc:  # noqa: BLE001 - any adapter/provider failure is a 502
        raise ProviderUnavailable(
            f"Could not read {what} for '{getattr(ticket, 'external_id', '?')}': {exc}"
        ) from exc
    project_wide = bool(project_wide_attr and getattr(adapter, project_wide_attr, False))
    return ProviderRead(list(items or []), True, project_wide)


def list_comments(db: Session, ticket: Any) -> ProviderRead:
    """This ticket's comments, live from the provider, as ``[{who, when, text}]``.

    Same shape as the ``comments`` snapshot ``GET /tickets/{id}`` returns, on
    purpose — an agent should not have to handle two shapes for one concept.
    This one is *current*; that one is as of ``syncedAt``.
    """
    return _read(
        db,
        ticket,
        capability="supports_comments",
        call=lambda adapter: adapter.fetch_comments(ticket.external_id),
        what="comments",
    )


def list_test_cases(db: Session, ticket: Any) -> ProviderRead:
    """Provider-side test cases as ``[{external_id, title, state}]``.

    **Not necessarily scoped to this ticket** — Azure DevOps has no cheap
    per-work-item query and answers project-wide, which the returned
    ``project_wide`` reports. The ticket is how the *connection* is resolved, and
    a hint the adapter may ignore. Flagged rather than merely documented because a
    caller that assumes scoping silently over-counts.
    """
    return _read(
        db,
        ticket,
        capability="supports_test_cases",
        call=lambda adapter: adapter.list_test_cases(ticket.external_id),
        what="test cases",
        project_wide_attr="test_cases_project_wide",
    )


# ------------------------------------------------------------------------ writes
# Every shipped adapter really implements all three of these, so there are no
# capability flags here — unlike the reads, where two providers have no test-case
# concept. The base class raises for anything it cannot do rather than no-opping.


def _write(what: str, external_id: str, call: Callable[[], Any]) -> Any:
    """Run one provider write, normalising failure to :class:`ProviderUnavailable`.

    Every provider rejection arrives here as an exception carrying the provider's
    own reason, and that reason is propagated verbatim: an agent shows it to a
    human, so replacing it with a generic message loses the only actionable part.
    """
    try:
        return call()
    except (ProviderUnavailable, AdapterLayerMissing, NoWorkItemConnection):
        raise
    except Exception as exc:  # noqa: BLE001 - any adapter/provider failure
        raise ProviderUnavailable(f"Could not {what} for '{external_id}': {exc}") from exc


def publish_comment(
    db: Session,
    ticket: Any,
    *,
    body: str,
    attachments: list[str] | None = None,
    author: str = "",
) -> str:
    """Post a comment on the work item. Returns the provider's comment id.

    Also appends it to the ticket's stored ``comments``, so a subsequent
    ``GET /tickets/{id}`` reflects a comment the hub itself just published rather
    than waiting for the next sync to discover it.
    """
    adapter = resolve_adapter(db, ticket)
    external_comment_id = _write(
        "publish a comment",
        ticket.external_id,
        lambda: adapter.publish_comment(ticket.external_id, body, attachments=attachments or None),
    )

    # Mirror it locally. Same {who, when, text} shape sync produces, so the
    # snapshot stays homogeneous.
    stored = list(ticket.comments or [])
    stored.append(
        {
            "who": author,
            "when": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            "text": body,
        }
    )
    ticket.comments = stored
    db.add(ticket)
    db.commit()
    db.refresh(ticket)
    return str(external_comment_id or "")


def transition(db: Session, ticket: Any, *, target_status: str) -> Any:
    """Transition the work item, then bring the hub's own row into line.

    The local update happens **only** after the provider call returns without
    raising — the hub must not record a status the provider does not have. The
    base adapter raises rather than no-opping for exactly this reason.
    """
    adapter = resolve_adapter(db, ticket)
    _write(
        f"transition to '{target_status}'",
        ticket.external_id,
        lambda: adapter.update_status(ticket.external_id, target_status),
    )
    ticket.status = target_status
    db.add(ticket)
    db.commit()
    db.refresh(ticket)
    return ticket


def create_test_cases(
    db: Session,
    ticket: Any,
    *,
    cases: list[CaseRequest],
    link: bool = True,
) -> list[CaseResult]:
    """Create provider-side test cases for this ticket, one result per case.

    **Never raises for a single rejected case**, because partial success is
    normal: one unsupported field or one duplicate title must not discard the
    cases that were created before it. A failure that prevents *any* case being
    attempted — an unroutable ticket, an undecryptable PAT — still raises, since
    then there is nothing partial about it.
    """
    adapter = resolve_adapter(db, ticket)
    results: list[CaseResult] = []
    for case in cases:
        try:
            created = adapter.create_test_case(
                ticket.external_id,
                title=case.title,
                precondition=case.precondition,
                steps=list(case.steps or []),
                priority=case.priority,
                link=link,
            ) or {}
        except Exception as exc:  # noqa: BLE001 - per-case, so the batch continues
            results.append(CaseResult(title=case.title, error=str(exc)[:200]))
            continue
        results.append(
            CaseResult(
                title=case.title,
                external_id=str(created.get("external_id", "")),
                url=str(created.get("url", "")),
                status=str(created.get("status", "")),
                linked=bool(created.get("linked")),
            )
        )
    return results
