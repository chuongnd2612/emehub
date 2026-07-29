"""Provider connection endpoints.

```
GET    /connections                            -> list[ConnectionOut]
POST   /connections                            -> ConnectionOut          (201)
PATCH  /connections/{id}                       -> ConnectionOut
DELETE /connections/{id}                       -> 204
POST   /connections/{id}/test                  -> ConnectionTestResult
GET    /connections/{id}/sprints               -> list[SprintOut]
GET    /connections/{id}/projects              -> list[ConnectionProjectOut]
GET    /connections/{id}/work-item-metadata    -> WorkItemMetadataOut
GET    /connections/{id}/repos                 -> AvailableReposOut
```

## The PAT never appears in a response

There is no schema in this module with a field that can hold one. ``ConnectionOut``
carries ``hasPat: bool`` and nothing else about the credential (CLAUDE.md ›
"Endpoints return ``hasPat: true``, never the PAT"; INTEGRATION.md §4). The
encrypted column is read in exactly one place —
``connection_service.adapter_for`` — and the plaintext never leaves that call.
``config`` *is* echoed back, so writes reject credential-shaped keys outright
rather than trusting the client not to park a token there.

## Auth posture: CONTRACT, tightened per route

Registered with ``CONTRACT`` in ``main.ROUTERS``, which applies a blanket
``Depends(require_principal)``. ``GET /connections`` is in the integration
contract (INTEGRATION.md §3): an agent calls it with its own token, whose ``aud``
is ``qagent`` / ``dagent``, so ``require_user`` would reject the very callers the
contract promises. Every other route here **manages** the hub — creating a
connection, storing a credential, spending a provider call — and declares
``Depends(require_user)`` on top, so a hub token is required. An agent token
therefore reads the catalogue and can do nothing else.

``CONTRACT`` rather than ``MIXED`` on purpose: ``MIXED`` applies no blanket
dependency, so a future route added here without one would be protected by the
guard middleware alone. This way the floor is authentication for everyone, and
each route can only tighten.

Metadata reads (``/sprints``, ``/projects``, ``/work-item-metadata``, ``/repos``)
each cause the hub to spend the PAT against the provider, so they are hub-only
until ``POST /connections/{id}/proxy`` is designed (deferred — INTEGRATION.md §4).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import Field
from sqlalchemy.orm import Session

from app import crypto
from app.db import get_db, utcnow
from app.deps_auth import require_principal, require_user
from app.logging import logger
from app.models.provider_connection import (
    PROVIDER_KINDS,
    REPOSITORY,
    WORK_ITEM,
    ProviderConnection,
)
from app.models.user import User
from app.schemas import ApiModel
from app.services import audit_service, connection_service
from app.services.adapters.base import ProviderAdapter, ProviderError
from app.services.ownership import can_write_shared, get_owned_or_404

router = APIRouter(prefix="/connections", tags=["connections"])


# ----------------------------------------------------------------- schemas
class ConnectionOut(ApiModel):
    """A provider connection as the wire sees it.

    Deliberately has no PAT field, and never will. ``hasPat`` is the entire
    truth an API response is allowed to tell about the stored credential.
    """

    id: int
    kind: str
    label: str = ""
    base_url: str = ""
    #: Non-secret adapter fields. Credential-shaped keys are rejected on write.
    config: dict[str, Any] = Field(default_factory=dict)
    #: ``work_item`` and/or ``repository`` — what this connection may be bound to.
    capabilities: list[str] = Field(default_factory=list)
    #: Everything the kind's adapter could do; the UI offers these as options.
    supported_capabilities: list[str] = Field(default_factory=list)
    #: Whether a credential is stored. Never the credential.
    has_pat: bool = False
    connected: bool = False
    #: ``True`` when the connection lives in the workspace-wide shared namespace.
    shared: bool = False
    last_sync: datetime | None = None
    last_tested_at: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class ConnectionCreate(ApiModel):
    kind: str
    label: str = ""
    base_url: str = ""
    config: dict[str, Any] = Field(default_factory=dict)
    #: Stored encrypted, immediately. Write-only — no response echoes it back.
    pat: str | None = None
    #: ``None`` takes the kind's defaults.
    capabilities: list[str] | None = None
    #: Create in the shared namespace instead of privately. Admins only.
    shared: bool = False


class ConnectionUpdate(ApiModel):
    """Every field optional. An omitted field is left alone — in particular an
    omitted ``pat`` keeps the stored credential, so the UI can save a label
    without re-typing the token. Sending ``""`` clears it."""

    label: str | None = None
    base_url: str | None = None
    config: dict[str, Any] | None = None
    pat: str | None = None
    capabilities: list[str] | None = None


class ConnectionTestResult(ApiModel):
    ok: bool = False
    message: str = ""
    detail: dict[str, Any] = Field(default_factory=dict)
    #: Round-trip to the provider, in milliseconds.
    latency_ms: int = 0


class SprintOut(ApiModel):
    id: str = ""
    name: str = ""
    #: Provider-native identifier — pass back as ``sprint_path`` when syncing.
    path: str = ""
    start_date: str | None = None
    finish_date: str | None = None
    state: str | None = None


class ConnectionProjectOut(ApiModel):
    external_id: str = ""
    name: str = ""
    state: str = ""


class AreaPathOut(ApiModel):
    id: str = ""
    name: str = ""
    path: str = ""


class EpicOut(ApiModel):
    key: str = ""
    name: str = ""


class WorkItemMetadataOut(ApiModel):
    area_paths: list[AreaPathOut] = Field(default_factory=list)
    work_item_types: list[str] = Field(default_factory=list)
    states: list[str] = Field(default_factory=list)
    epics: list[EpicOut] = Field(default_factory=list)


class RepoOut(ApiModel):
    name: str = ""
    clone_url: str = ""
    web_url: str = ""
    default_branch: str = ""


class AvailableReposOut(ApiModel):
    """The repo picker's wrapper: an upstream hiccup is a message, not a 500."""

    provider: str = ""
    repos: list[RepoOut] = Field(default_factory=list)
    error: str = ""


# ----------------------------------------------------------------- helpers
def _out(conn: ProviderConnection) -> ConnectionOut:
    """Serialise a connection. The one function that decides what leaves the hub.

    Built field-by-field rather than by ``model_validate(conn)`` so that adding a
    column to the model can never silently start returning it.
    """
    return ConnectionOut(
        id=conn.id,
        kind=conn.kind,
        label=conn.label,
        base_url=conn.base_url,
        config=dict(conn.config or {}),
        capabilities=list(conn.capabilities or []),
        supported_capabilities=list(connection_service.supported_capabilities(conn.kind)),
        has_pat=conn.has_pat,
        connected=conn.connected,
        shared=conn.shared,
        last_sync=conn.last_sync,
        last_tested_at=conn.last_tested_at,
        created_at=conn.created_at,
        updated_at=conn.updated_at,
    )


def _bad_request(exc: ValueError) -> HTTPException:
    return HTTPException(status_code=400, detail=str(exc))


def _load(db: Session, connection_id: int, user: User) -> ProviderConnection:
    """Fetch scoped to ``user``. Another member's connection 404s rather than
    403s — a 403 confirms the row exists, which is itself a disclosure."""
    return get_owned_or_404(db, ProviderConnection, connection_id, user)


def _require_writable(conn: ProviderConnection, user: User) -> None:
    """Only an admin may modify a shared connection.

    A shared connection is workspace-wide infrastructure: any member can *use*
    it, but a member editing its URL or replacing its PAT would silently change
    what everyone else's runs authenticate as.
    """
    if conn.shared and not can_write_shared(user):
        raise HTTPException(
            status_code=403, detail="Only an admin may modify a shared connection"
        )


def _require_capability(conn: ProviderConnection, capability: str) -> None:
    if not conn.advertises(capability):
        raise HTTPException(
            status_code=400,
            detail=(
                f"Connection {conn.id} ({conn.kind}) does not supply "
                f"'{capability}'"
            ),
        )


def _adapter(conn: ProviderConnection) -> ProviderAdapter:
    return connection_service.adapter_for(conn)


# ------------------------------------------------------------------- routes
@router.get("", response_model=list[ConnectionOut])
def list_connections(
    principal: User = Depends(require_principal),
    db: Session = Depends(get_db),
) -> list[ConnectionOut]:
    """Connections visible to the caller, with their capabilities.

    INTEGRATION.md §3. Reachable with an *agent* token as well as a hub one,
    because an agent needs to know which connections exist and what each one can
    supply. It never includes the PAT — until the proxy in §4 exists, this
    endpoint is informational and agents keep their own provider credentials.
    """
    rows = connection_service.list_connections(db, principal.id)
    return [_out(conn) for conn in rows]


@router.post("", response_model=ConnectionOut, status_code=201)
def create_connection(
    body: ConnectionCreate,
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
) -> ConnectionOut:
    """Create a connection, encrypting the PAT before it is ever persisted."""
    if body.kind not in PROVIDER_KINDS:
        raise HTTPException(status_code=400, detail=f"Unknown provider kind '{body.kind}'")
    if body.shared and not can_write_shared(user):
        raise HTTPException(
            status_code=403, detail="Only an admin may create a shared connection"
        )
    try:
        capabilities = connection_service.normalize_capabilities(body.kind, body.capabilities)
        connection_service.reject_secret_like_config(body.config)
    except ValueError as exc:
        raise _bad_request(exc) from exc

    conn = ProviderConnection(
        kind=body.kind,
        label=body.label.strip(),
        base_url=(body.base_url or "").strip(),
        config=body.config or {},
        # Encrypted here, on the way in. A plaintext PAT never reaches the DB.
        pat_encrypted=crypto.encrypt(body.pat) if body.pat else None,
        capabilities=capabilities,
        connected=False,
        # NULL == shared; otherwise private to the creator.
        owner_id=None if body.shared else user.id,
    )
    db.add(conn)
    db.commit()
    db.refresh(conn)
    audit_service.record(
        category="connection",
        action="Added provider connection",
        target=conn.display_name,
        actor=user.email,
        actor_id=user.id,
        owner_id=conn.owner_id,
        detail={"kind": conn.kind, "capabilities": capabilities},
        db=db,
    )
    return _out(conn)


@router.patch("/{connection_id}", response_model=ConnectionOut)
def update_connection(
    connection_id: int,
    body: ConnectionUpdate,
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
) -> ConnectionOut:
    """Update a connection. An omitted ``pat`` keeps the stored one; ``""`` clears it."""
    conn = _load(db, connection_id, user)
    _require_writable(conn, user)

    if body.label is not None:
        conn.label = body.label.strip()
    if body.base_url is not None:
        conn.base_url = body.base_url.strip()
    if body.config is not None:
        try:
            connection_service.reject_secret_like_config(body.config)
        except ValueError as exc:
            raise _bad_request(exc) from exc
        conn.config = {**(conn.config or {}), **body.config}
    if body.capabilities is not None:
        try:
            conn.capabilities = connection_service.normalize_capabilities(
                conn.kind, body.capabilities
            )
        except ValueError as exc:
            raise _bad_request(exc) from exc
    # `pat` in the payload at all is the signal — distinguishing "" (clear) from
    # absent (keep) needs the set of fields the client actually sent.
    if "pat" in body.model_fields_set:
        conn.pat_encrypted = crypto.encrypt(body.pat) if body.pat else None
        # A replaced credential is unproven until it is tested again.
        conn.connected = False

    db.commit()
    db.refresh(conn)
    audit_service.record(
        category="connection",
        action="Updated provider connection",
        target=conn.display_name,
        actor=user.email,
        actor_id=user.id,
        owner_id=conn.owner_id,
        # The names of the fields that changed — never their values.
        meta=", ".join(sorted(body.model_fields_set)),
        db=db,
    )
    return _out(conn)


@router.delete("/{connection_id}", status_code=204)
def delete_connection(
    connection_id: int,
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
) -> Response:
    """Delete a connection and the credential it holds."""
    conn = _load(db, connection_id, user)
    _require_writable(conn, user)
    name, owner_id = conn.display_name, conn.owner_id
    db.delete(conn)
    db.commit()
    audit_service.record(
        category="connection",
        action="Removed provider connection",
        target=name,
        actor=user.email,
        actor_id=user.id,
        owner_id=owner_id,
        db=db,
    )
    return Response(status_code=204)


@router.post("/{connection_id}/test", response_model=ConnectionTestResult)
def test_connection(
    connection_id: int,
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
) -> ConnectionTestResult:
    """Probe the provider with the stored credential and record the verdict."""
    conn = _load(db, connection_id, user)
    started = utcnow()
    try:
        result = _adapter(conn).test_connection()
    except ProviderError as exc:
        result = {"ok": False, "message": str(exc), "detail": {}}
    latency_ms = int((utcnow() - started).total_seconds() * 1000)

    conn.connected = bool(result.get("ok"))
    conn.last_tested_at = utcnow()
    db.commit()

    audit_service.record(
        category="connection",
        action="Tested provider connection",
        target=conn.display_name,
        actor=user.email,
        actor_id=user.id,
        owner_id=conn.owner_id,
        status="success" if conn.connected else "error",
        meta=str(result.get("message", "")),
        db=db,
    )
    return ConnectionTestResult(
        ok=bool(result.get("ok")),
        message=str(result.get("message", "")),
        detail=result.get("detail") or {},
        latency_ms=latency_ms,
    )


@router.get("/{connection_id}/sprints", response_model=list[SprintOut])
def list_sprints(
    connection_id: int,
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
) -> list[SprintOut]:
    """Sprints / iterations for a work-item connection.

    Degrades to an empty list on an upstream failure: the sprint picker showing
    nothing is recoverable, the picker erroring is not.
    """
    conn = _load(db, connection_id, user)
    _require_capability(conn, WORK_ITEM)
    try:
        sprints = _adapter(conn).list_sprints()
    except Exception as exc:  # noqa: BLE001 - a provider hiccup must not 500 a picker
        _log_unavailable("sprints", conn, exc)
        return []
    return [SprintOut.model_validate(s) for s in sprints]


@router.get("/{connection_id}/projects", response_model=list[ConnectionProjectOut])
def list_projects(
    connection_id: int,
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
) -> list[ConnectionProjectOut]:
    """Projects visible under the connection's organisation."""
    conn = _load(db, connection_id, user)
    _require_capability(conn, WORK_ITEM)
    try:
        projects = _adapter(conn).list_projects()
    except Exception as exc:  # noqa: BLE001
        _log_unavailable("projects", conn, exc)
        return []
    return [ConnectionProjectOut.model_validate(p) for p in projects]


@router.get("/{connection_id}/work-item-metadata", response_model=WorkItemMetadataOut)
def work_item_metadata(
    connection_id: int,
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
) -> WorkItemMetadataOut:
    """Filter options — area paths, work item types, states, epics."""
    conn = _load(db, connection_id, user)
    _require_capability(conn, WORK_ITEM)
    try:
        meta = _adapter(conn).list_work_item_metadata()
    except Exception as exc:  # noqa: BLE001
        _log_unavailable("work-item metadata", conn, exc)
        return WorkItemMetadataOut()
    return WorkItemMetadataOut.model_validate(meta)


@router.get("/{connection_id}/repos", response_model=AvailableReposOut)
def list_repos(
    connection_id: int,
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
) -> AvailableReposOut:
    """Repositories a repository connection exposes.

    Returns the ``{provider, repos, error}`` wrapper so the picker can say *why*
    it is empty instead of rendering a blank list with no explanation.
    """
    conn = _load(db, connection_id, user)
    _require_capability(conn, REPOSITORY)
    try:
        repos = _adapter(conn).list_repos()
    except ProviderError as exc:
        return AvailableReposOut(provider=conn.kind, error=str(exc))
    except Exception as exc:  # noqa: BLE001
        _log_unavailable("repos", conn, exc)
        return AvailableReposOut(provider=conn.kind, error="Could not list repositories")
    return AvailableReposOut(
        provider=conn.kind, repos=[RepoOut.model_validate(r) for r in repos]
    )


def _log_unavailable(what: str, conn: ProviderConnection, exc: Exception) -> None:
    """Log an upstream failure by connection **id and kind only**.

    Never the config, never the exception's request — an adapter's exception can
    carry a URL, and a log line is the easiest place for a credential to end up
    where nobody looks for it. ``ProviderError`` messages are already scrubbed by
    ``adapters.base.scrub``; anything else is reduced to its type.
    """
    reason = str(exc) if isinstance(exc, ProviderError) else type(exc).__name__
    logger.warning(
        "Provider %s unavailable for connection %s (%s): %s",
        what,
        conn.id,
        conn.kind,
        reason,
    )
