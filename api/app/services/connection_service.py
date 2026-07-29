"""Provider connections — visibility, capability routing and adapter construction.

Ported from QAgent's ``services/connection_service.py``. Credentials are routed
along two independent paths, which is the whole reason capabilities exist:

* **Work-item** work (ticket fetch, comment publish, status transition) routes
  through the *ticket's* connection — its stamped ``connection_id``, else the
  first work-item connection of its ``provider_kind``.
* **Repository** work (clone, knowledge build, repo discovery) routes through
  the *project's* bound repository connection, else the first repository-capable
  connection.

So one project can take its tickets from Jira and its code from GitHub, and an
Azure DevOps connection can serve both jobs at once.

## This module is the only place the PAT is decrypted

Two functions decrypt, and both live here on purpose: :func:`adapter_for`, for a
provider API call, and :func:`repository_pat`, for the ``git clone`` a hub-side
knowledge build performs (ADR 0007). Everything above them — the routers, the
schemas, ``repo_service`` — never touches ``pat_encrypted``, and the plaintext
lives only as a local for the length of one call. Nothing here logs a
connection's secret, its config or its adapter.

The clone path is the sharper of the two: a PAT injected into an HTTPS URL is a
secret inside a string that git happily echoes into its own error output. See
:func:`repository_pat` and ``repo_service`` for the scrubbing that answers it.

## Visibility

Every lookup is scoped by ``viewer_id`` and means the same thing everywhere:
**the viewer's own connections plus the shared (``owner_id IS NULL``) namespace,
never another member's.** ``viewer_id=None`` resolves to the shared namespace
only — the hub never has a "see everything" mode (CLAUDE.md › Never fail open).
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

import httpx
from sqlalchemy import or_
from sqlalchemy.orm import Query, Session

from app import crypto
from app.models.provider_connection import (
    CAPABILITIES,
    PROVIDER_KINDS,
    REPOSITORY,
    SUPPORTED_CAPABILITIES,
    WORK_ITEM,
    ProviderConnection,
    default_capabilities,
    supported_capabilities,
)
from app.services.adapters import get_adapter
from app.services.adapters.base import ProviderAdapter, ProviderError

__all__ = [
    "CAPABILITIES",
    "PROVIDER_KINDS",
    "REPOSITORY",
    "SUPPORTED_CAPABILITIES",
    "WORK_ITEM",
    "TicketLike",
    "adapter_config",
    "adapter_for",
    "connections_with_capability",
    "default_capabilities",
    "get_connection",
    "normalize_capabilities",
    "reject_secret_like_config",
    "repository_pat",
    "resolve_repository_for_project",
    "resolve_work_item_for_ticket",
    "supported_capabilities",
    "visible",
]


@runtime_checkable
class TicketLike(Protocol):
    """What :func:`resolve_work_item_for_ticket` needs from a ticket.

    Structural rather than an import of the ticket model: connections ship
    before tickets do, and the tickets slice should depend on this module, not
    the other way round.
    """

    #: The connection this ticket was synced through, if it was stamped.
    connection_id: int | None
    #: ``azure_devops`` | ``github`` | ``jira``.
    provider_kind: str
    #: The ticket's owner; ``None`` for a shared ticket.
    owner_id: int | None


# ------------------------------------------------------------------ visibility
def visible(query: Query, viewer_id: int | None) -> Query:
    """Restrict a ``ProviderConnection`` query to what ``viewer_id`` may see.

    Mirrors :func:`app.services.ownership.owned`, but takes a user *id* rather
    than a ``User`` — the resolution helpers are called from background work
    that holds an id and no ORM user. ``None`` yields the shared namespace only.
    """
    if viewer_id is None:
        return query.filter(ProviderConnection.owner_id.is_(None))
    return query.filter(
        or_(
            ProviderConnection.owner_id == viewer_id,
            ProviderConnection.owner_id.is_(None),
        )
    )


def list_connections(db: Session, viewer_id: int | None) -> list[ProviderConnection]:
    """Every connection ``viewer_id`` may see, in creation order."""
    return visible(db.query(ProviderConnection), viewer_id).order_by(ProviderConnection.id).all()


def get_connection(
    db: Session, connection_id: int | None, viewer_id: int | None = None
) -> ProviderConnection | None:
    """A connection by id, or ``None`` — including when it exists but the viewer
    may not see it. Absence and inaccessibility are deliberately the same answer;
    distinguishing them tells the caller the row exists."""
    if not connection_id:
        return None
    return (
        visible(db.query(ProviderConnection), viewer_id)
        .filter(ProviderConnection.id == connection_id)
        .first()
    )


def connections_with_capability(
    db: Session, capability: str, viewer_id: int | None = None
) -> list[ProviderConnection]:
    """Visible connections advertising ``capability``, in creation order.

    Filtered in Python rather than SQL: ``capabilities`` is a portable
    ``sa.JSON`` column (the test suite runs the same migrations on SQLite), and
    SQLite has no JSON containment operator. The table is small — a workspace
    holds connections in the tens, not the millions.
    """
    return [
        conn
        for conn in list_connections(db, viewer_id)
        if capability in (conn.capabilities or [])
    ]


def _first_with_capability(
    db: Session, capability: str, viewer_id: int | None
) -> ProviderConnection | None:
    matches = connections_with_capability(db, capability, viewer_id)
    return matches[0] if matches else None


def first_of_kind(
    db: Session, kind: str, viewer_id: int | None = None
) -> ProviderConnection | None:
    """The first visible connection of ``kind``, or ``None``."""
    return (
        visible(db.query(ProviderConnection), viewer_id)
        .filter(ProviderConnection.kind == kind)
        .order_by(ProviderConnection.id)
        .first()
    )


# ------------------------------------------------------------------ validation
def normalize_capabilities(kind: str, requested: list[str] | None) -> list[str]:
    """Validate a requested capability list against what ``kind`` implements.

    ``None`` means "the kind's defaults". An empty list is refused — a connection
    that advertises nothing can never be selected for any job, which is a
    configuration mistake rather than a valid state.

    Raises:
        ValueError: an unknown capability, or one the kind's adapter cannot do.
    """
    supported = supported_capabilities(kind)
    if not supported:
        raise ValueError(f"Unknown provider kind '{kind}'")
    if requested is None:
        return list(supported)
    wanted = list(dict.fromkeys(requested))  # de-duplicate, keep order
    if not wanted:
        raise ValueError("A connection must advertise at least one capability")
    for capability in wanted:
        if capability not in CAPABILITIES:
            raise ValueError(f"Unknown capability '{capability}'")
        if capability not in supported:
            raise ValueError(f"Provider '{kind}' cannot supply '{capability}'")
    return [c for c in supported if c in wanted]  # canonical order


#: Substrings that mark a config key as credential-shaped. ``config`` is echoed
#: back verbatim by ``GET /connections``, so a secret parked there would be a
#: secret in a response body — the exact failure this slice exists to prevent.
_SECRET_LIKE = (
    "pat",
    "token",
    "secret",
    "password",
    "passwd",
    "pwd",
    "apikey",
    "api_key",
    "credential",
    "private",
)


def reject_secret_like_config(config: dict[str, Any] | None) -> None:
    """Raise :class:`ValueError` if a config key looks like it holds a secret.

    The PAT has exactly one home — the encrypted column. Refusing the shape at
    the door beats discovering it in a response body later.
    """
    for key in (config or {}):
        lowered = str(key).lower().replace("-", "").replace("_", "")
        if any(marker.replace("_", "") in lowered for marker in _SECRET_LIKE):
            raise ValueError(
                f"'{key}' looks like a secret — secrets belong in the encrypted "
                "PAT field, never in config"
            )


# --------------------------------------------------------------------- adapters
def adapter_config(connection: ProviderConnection) -> dict[str, Any]:
    """The non-secret dict an adapter is constructed with.

    Flattens the ``base_url`` column into both ``baseUrl`` and ``orgUrl`` so each
    adapter can read whichever name its provider's documentation uses, without
    the model growing a per-provider column.
    """
    config = dict(connection.config or {})
    config.setdefault("baseUrl", connection.base_url or "")
    config.setdefault("orgUrl", connection.base_url or "")
    return config


def adapter_for(
    connection: ProviderConnection,
    *,
    transport: httpx.BaseTransport | None = None,
) -> ProviderAdapter:
    """Build a live adapter for ``connection``.

    **The only place a stored PAT is decrypted.** The plaintext exists as a local
    for the length of this call and is handed straight to the adapter; it is
    never returned, logged or stored.

    Args:
        transport: an ``httpx`` transport override. **Tests only** — product code
            never passes one, so there is no mock path in the product (ADR 0001).

    Raises:
        ProviderError: the stored PAT cannot be decrypted under the current
            ``EMEHUB_ENCRYPTION_KEY``. ``crypto.decrypt`` returns ``None`` for a
            ciphertext that does not authenticate, and that must surface as
            "unavailable" — never be passed on as an empty credential, which
            would read as "no PAT configured" and hide a key-rotation accident.
    """
    pat = crypto.decrypt(connection.pat_encrypted)
    if connection.pat_encrypted and pat is None:
        raise ProviderError(
            f"The stored credential for '{connection.display_name}' cannot be "
            "decrypted with the current encryption key"
        )
    return get_adapter(
        connection.kind,
        adapter_config(connection),
        {"pat": pat or ""},
        transport=transport,
    )


def repository_pat(connection: ProviderConnection) -> str:
    """The decrypted PAT for a clone, or ``""`` when the connection carries none.

    The second — and last — decryption point in the hub (ADR 0007). Split from
    :func:`adapter_for` because a clone needs the raw token to inject into an
    HTTPS URL rather than an adapter that knows how to send it.

    An unset PAT yields ``""`` so a **public** repository still clones. An
    undecryptable one does not: that is a key-rotation accident, and passing it
    on as "no credential" would turn it into a confusing 404-from-git instead of
    the operational error it is.

    Raises:
        ProviderError: the stored PAT does not decrypt under the current
            ``EMEHUB_ENCRYPTION_KEY``.
    """
    if not connection.pat_encrypted:
        return ""
    pat = crypto.decrypt(connection.pat_encrypted)
    if pat is None:
        raise ProviderError(
            f"The stored credential for '{connection.display_name}' cannot be "
            "decrypted with the current encryption key"
        )
    return pat


# ------------------------------------------------------------- work-item routing
def resolve_work_item_for_ticket(db: Session, ticket: TicketLike) -> ProviderConnection:
    """The work-item connection a ticket's provider work routes through.

    Order: the ticket's stamped ``connection_id`` → the first work-item-capable
    connection of the ticket's ``provider_kind`` → :class:`ProviderError`.
    Everything is scoped to the ticket's own ``owner_id``, so a member's ticket
    can only ever route through that member's connections or the shared ones.

    A connection is only accepted if it *advertises* ``work_item``: a stamped id
    pointing at a repository-only connection is a misbinding, and falling through
    to the kind's default beats making a call the adapter has no path for.
    """
    viewer_id = getattr(ticket, "owner_id", None)
    conn = get_connection(db, getattr(ticket, "connection_id", None), viewer_id)
    if conn is not None and conn.advertises(WORK_ITEM):
        return conn
    kind = getattr(ticket, "provider_kind", "") or ""
    conn = first_of_kind(db, kind, viewer_id)
    if conn is not None and conn.advertises(WORK_ITEM):
        return conn
    raise ProviderError(f"No work-item connection is configured for '{kind}'")


# ------------------------------------------------------------ repository routing
def resolve_repository_for_project(
    db: Session,
    *,
    viewer_id: int | None = None,
    bound_connection_id: int | None = None,
) -> ProviderConnection:
    """The repository connection a project's code work routes through.

    Order: the project's bound connection → the first repository-capable visible
    connection → :class:`ProviderError`.

    ``bound_connection_id`` is passed in rather than looked up. QAgent read it
    from ``ProjectConfig``; here projects are a *separate* slice, and inverting
    the dependency keeps connections importable by tickets and projects alike
    without a cycle. The projects slice supplies the binding it holds.
    """
    conn = get_connection(db, bound_connection_id, viewer_id)
    if conn is not None and conn.advertises(REPOSITORY):
        return conn
    conn = _first_with_capability(db, REPOSITORY, viewer_id)
    if conn is not None:
        return conn
    raise ProviderError("No repository connection is configured")
