"""Provider connection endpoints.

```
GET    /connections                            -> list[ConnectionOut]
GET    /connections/{id}/secret                -> ConnectionSecretOut
POST   /connections                            -> ConnectionOut          (201)
PATCH  /connections/{id}                       -> ConnectionOut
DELETE /connections/{id}                       -> 204
POST   /connections/{id}/test                  -> ConnectionTestResult
GET    /connections/{id}/sprints               -> list[SprintOut]
GET    /connections/{id}/projects              -> list[ConnectionProjectOut]
GET    /connections/{id}/work-item-metadata    -> WorkItemMetadataOut
GET    /connections/{id}/repos                 -> AvailableReposOut
```

## The PAT appears in exactly one response, and it is not a connection

``ConnectionOut`` carries ``hasPat: bool`` and nothing else about the credential
(CLAUDE.md › "Endpoints return ``hasPat: true``, never the PAT"), and ``_out()``
builds it field by field so a new column can never silently start being returned.
That is unchanged and load-bearing.

``GET /connections/{id}/secret`` is the single deliberate exception (ADR 0010).
It has its **own** response model, its own route and its own audit trail, and it
is refused to the hub's own audience. The reason it exists is that DAgent hands
the credential to an MCP subprocess and to ``git`` — neither of which is a call
the hub can make on the agent's behalf, so the narrow-endpoint pattern that
covers every other provider operation has nothing to attach to here.

Two schemas rather than one optional field, on purpose: "does this response
carry a secret" stays a question you answer by reading the type, not by reading
a value at runtime.

``config`` *is* echoed back by both, so writes reject credential-shaped keys
outright rather than trusting the client not to park a token there.

## Auth posture: CONTRACT, tightened per route

Registered with ``CONTRACT`` in ``main.ROUTERS``, which applies a blanket
``Depends(require_principal)``. ``GET /connections`` is in the integration
contract (INTEGRATION.md §3): an agent calls it with its own token, whose ``aud``
is ``qagent`` / ``dagent``, so ``require_user`` would reject the very callers the
contract promises. ``GET /connections/{id}/secret`` is contract for the same
reason and goes further — it is the one route in the hub an agent token reaches
that a *hub* token does not. Every other route here **manages** the hub —
creating a connection, storing a credential, spending a provider call — and
declares ``Depends(require_user)`` on top, so a hub token is required. An agent
token therefore reads the catalogue, reads a credential, and does nothing else.

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

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import Field
from sqlalchemy.orm import Session

from app import crypto
from app.config import AUDIENCE_HUB
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
from app.schemas import ApiModel, OkResponse
from app.services import audit_service, connection_service, metadata_cache
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


class ConnectionSecretOut(ApiModel):
    """**The only schema in this module that carries a credential** (ADR 0010).

    Kept deliberately separate from :class:`ConnectionOut` rather than adding an
    optional field to it: ``_out()`` is the serialiser that must never leak, and
    a nullable ``pat`` on the shared shape would make "does this response carry a
    secret" a runtime question instead of a structural one. Two schemas, one of
    which is reachable from exactly one route.
    """

    id: int
    kind: str
    label: str = ""
    base_url: str = ""
    config: dict[str, Any] = Field(default_factory=dict)
    capabilities: list[str] = Field(default_factory=list)
    #: The decrypted PAT. The agent writes it into its own credential store and
    #: nowhere else; INTEGRATION.md §4 states the obligations that come with it.
    pat: str
    #: Bumped by ``onupdate`` on every write, a PAT rotation included. This is the
    #: agent's cache key: compare it against ``GET /connections`` and re-read this
    #: endpoint only for a connection that actually moved.
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


class ClassificationNodeOut(ApiModel):
    """One node of the area or iteration tree, flattened.

    Both are trees, and a picker has to indent them without walking a nested
    structure — so each node carries the full ``path`` a clause actually uses and
    its ``depth`` (0 for the project root), in pre-order.
    """

    id: str = ""
    name: str = ""
    path: str = ""
    depth: int = 0


class WorkItemTypeOut(ApiModel):
    """A work item type with **its own** states.

    States are grouped per type because a Bug and a User Story do not share a
    state set: offering ``Committed`` on a Bug builds a query that matches
    nothing, which reads to the user as "there is no work" rather than as the
    mistake it is.
    """

    name: str = ""
    states: list[str] = Field(default_factory=list)


class MemberOut(ApiModel):
    display_name: str = ""
    #: The account a query matches on, e.g. ``duna@emesoft.net``.
    unique_name: str = ""


class WorkItemMetadataOut(ApiModel):
    area_paths: list[ClassificationNodeOut] = Field(default_factory=list)
    iteration_paths: list[ClassificationNodeOut] = Field(default_factory=list)
    work_item_types: list[WorkItemTypeOut] = Field(default_factory=list)
    #: Every state across every type, for a picker that has not narrowed by type.
    states: list[str] = Field(default_factory=list)
    members: list[MemberOut] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    epics: list[EpicOut] = Field(default_factory=list)
    #: When the provider was really read — what "read 4 minutes ago" is computed
    #: from, and null when nothing has ever been read.
    fetched_at: datetime | None = None
    #: The TTL passed and the refresh we tried failed. The payload is the last good
    #: one, not an empty shell — so the panel stays usable and says why.
    stale: bool = False
    message: str = ""


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
    supply. It never includes the PAT — an agent that needs the credential itself
    reads :func:`connection_secret` per connection, and this list's ``updatedAt``
    is how it knows which ones to bother re-reading.
    """
    rows = connection_service.list_connections(db, principal.id)
    return [_out(conn) for conn in rows]


@router.get("/{connection_id}/secret", response_model=ConnectionSecretOut)
def connection_secret(
    connection_id: int,
    principal: User = Depends(require_principal),
    db: Session = Depends(get_db),
) -> ConnectionSecretOut:
    """**The one endpoint that returns a provider PAT** (ADR 0010).

    Every other provider operation an agent performs goes through a narrow
    endpoint where *the hub* makes the call, so the secret never has to move —
    ``POST /tickets/sync`` and the ``/tickets/{external_id}/…`` reads and writes.
    Two consumers have no such seam, both in DAgent: the config it hands to an
    MCP subprocess, and ``git`` against an authenticated remote. Neither is a call
    the hub can make on its behalf, so for those the credential crosses.

    What keeps it narrow:

    * **Agent audiences only.** The hub's own SPA deliberately never displays a
      PAT, so a browser origin must not be able to read one — the same guard
      ``POST /auth/agent-grant`` applies for the same reason.
    * **Scoped like every other connection read**, so another member's connection
      404s rather than 403s.
    * **Its own response model.** :func:`_out` is untouched and still cannot leak;
      this is the only serialiser in the module that is allowed to.
    * **Audited on every call** — success, miss and failure alike. This is the
      second endpoint in the hub that returns a secret, and the audit row is the
      only record that it happened.
    """
    audience = getattr(principal, "_aud", None) or ""
    if audience == AUDIENCE_HUB:
        raise HTTPException(
            status_code=400, detail="A connection secret is for an agent, not the hub"
        )
    conn = get_owned_or_404(db, ProviderConnection, connection_id, principal)

    def _audit(action: str, status: str) -> None:
        audit_service.record(
            category="credential",
            action=action,
            actor=principal.email,
            actor_id=principal.id,
            source=audience,
            target=f"connection:{conn.id}:{conn.kind}",
            status=status,
            owner_id=conn.owner_id,
            db=db,
        )

    if not conn.has_pat:
        _audit("Provider secret resolve found none", "warning")
        raise HTTPException(
            status_code=404, detail=f"Connection {conn.id} has no stored credential"
        )

    pat = crypto.decrypt(conn.pat_encrypted)
    if not pat:
        # Never pass an undecryptable blob on as if it were the credential — the
        # same rule the provider read-throughs apply, one level down.
        _audit("Provider secret could not be decrypted", "error")
        raise HTTPException(
            status_code=502,
            detail="The stored credential could not be decrypted with the current key",
        )

    _audit("Resolved a provider secret", "success")
    return ConnectionSecretOut(
        id=conn.id,
        kind=conn.kind,
        label=conn.label,
        base_url=conn.base_url,
        config=dict(conn.config or {}),
        capabilities=list(conn.capabilities or []),
        pat=pat,
        updated_at=conn.updated_at,
    )


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
    refresh: bool = Query(False, description="Read the provider again, ignoring the cache"),
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
) -> WorkItemMetadataOut:
    """Everything the query builder's pickers need, cached per connection.

    Served from the cache inside ``EMEHUB_METADATA_TTL_MINUTES``; ``?refresh=true``
    forces a read. A refresh that **fails** still returns the last good payload
    with ``stale: true`` and the reason — the values from an hour ago are almost
    certainly still right, and offering them beats an empty picker that silently
    builds a query matching nothing.
    """
    conn = _load(db, connection_id, user)
    _require_capability(conn, WORK_ITEM)
    adapter = _adapter(conn)
    try:
        result = metadata_cache.read(
            db, conn, adapter.list_work_item_metadata, refresh=refresh
        )
    except Exception as exc:  # noqa: BLE001 — a first read with nothing cached
        _log_unavailable("work-item metadata", conn, exc)
        return WorkItemMetadataOut(stale=True, message=str(exc) or "The provider did not answer.")
    return WorkItemMetadataOut.model_validate(
        {
            **result.payload,
            "fetched_at": result.fetched_at,
            "stale": result.stale,
            "message": result.message,
        }
    )


@router.delete("/{connection_id}/metadata/cache", response_model=OkResponse)
def clear_metadata_cache(
    connection_id: int,
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
) -> OkResponse:
    """Drop this connection's cached metadata.

    ``?refresh=true`` covers the ordinary "these look out of date" case; this is
    for the other one — a payload that is *wrong* rather than merely old, after the
    project was reconfigured on the provider side.
    """
    conn = _load(db, connection_id, user)
    metadata_cache.clear(db, conn.id)
    return OkResponse()


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
