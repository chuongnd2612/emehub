"""Claude credentials — the one secret the hub deliberately hands out.

INTEGRATION.md §4: ``GET /credentials/claude/resolve`` returns credential
material an agent writes to a private ``CLAUDE_CONFIG_DIR``. Everything in this
module exists to make that the *only* leak, and a recorded one.

## Posture — ``GRANTED``, tightened per route

The router is registered ``GRANTED`` in :data:`app.main.ROUTERS`, because three of
its endpoints are in the integration contract and an agent calls them with the
token it already holds (``aud: "qagent"`` / ``"dagent"``) — or, past that token's
15-minute life, with a run-scoped credential grant (ADR 0009):

* ``GET  /credentials/claude/resolve``   — the credential to run with;
* ``PUT  /credentials/claude/refreshed`` — the CLI's rotated token, posted back
  so the hub stays authoritative (INTEGRATION.md §4);
* ``POST /credentials/claude/usage``     — one completed call's spend.

**These three are the *only* routes in the hub a grant can reach**, and that is
enforced by this wiring rather than by a check inside the grant: nowhere else
depends on ``require_credential_grant``, and a grant's audience is never
registerable, so ``require_principal`` and ``require_user`` both refuse it.

The blanket dependency is the loosest one any route here needs, because every
route's own dependency *also* runs and the stricter one decides. So every
management endpoint declares ``Depends(require_user)`` (hub audience only) or
``Depends(require_admin)`` on top — a grant, or a bare agent token, can fetch a
credential but cannot manage one. ``PROTECTED`` is not an option: its blanket
``require_user`` would reject the very agent tokens ``/resolve`` exists for.

## Why nothing else leaks the token

The service layer builds every metadata response field by field from the parsed
columns and never reads ``row.credentials``; the single decrypt lives in
``claude_credentials.resolve_material``, whose single caller is
:func:`resolve_credential` below. The response models here make that structural:
:class:`ResolvedCredentialOut` is the only schema in the module with a
credential-bearing field, and every other endpoint is annotated with a
``response_model`` that has none — so even a mistake in a handler cannot
serialise a token. Nothing in this module logs a request body.
"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import Field
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps_auth import require_admin, require_credential_grant, require_user
from app.models.user import User
from app.schemas import ApiModel, OkResponse
from app.services import audit_service, claude_credentials, claude_usage
from app.services.claude_credentials import ClaudeCredentialsError

router = APIRouter(prefix="/credentials/claude", tags=["credentials"])


# ---------------------------------------------------------------- schemas
class CredentialUpload(ApiModel):
    """The raw contents of a Claude CLI ``.credentials.json``, plus a label.

    ``credentials`` is write-only: it appears in no response model in this
    module.
    """

    credentials: str
    label: str = ""


class CredentialMetaOut(ApiModel):
    """Metadata for one stored credential. **No credential material.**"""

    label: str = ""
    status: str = "active"
    stored_status: str = "active"
    expires_at: datetime | None = None
    days_left: int | None = None
    scopes: list[str] = Field(default_factory=list)
    subscription_type: str | None = None
    last_refreshed: datetime | None = None
    prefer_shared: bool = False
    #: Whether the stored file carries a refresh token, so the SPA can derive
    #: the same status the hub did (issue #63). The presence, never the token.
    has_refresh_token: bool = False
    #: Shared row only — active users with no credential of their own.
    assigned_users: int | None = None


class CredentialStatusOut(ApiModel):
    """``GET /credentials/claude`` — what is configured and what will be used."""

    has_own: bool = False
    has_shared: bool = False
    mode: str = "none"
    prefer_shared: bool = False
    own: CredentialMetaOut | None = None
    shared: CredentialMetaOut | None = None


class CredentialModeUpdate(ApiModel):
    mode: str


class CredentialTestOut(ApiModel):
    ok: bool = False
    result: str = "no_credential"
    message: str = ""


class ResolvedCredentialOut(ApiModel):
    """**The only response model in the hub that carries credential material.**

    ``credentials`` is the decrypted ``.credentials.json`` text. Per
    INTEGRATION.md §4 the agent must write it only into the CLI's own config dir
    and never persist it in plaintext elsewhere.
    """

    source: str
    credentials: str
    label: str = ""
    status: str = "active"
    expires_at: datetime | None = None
    days_left: int | None = None
    scopes: list[str] = Field(default_factory=list)
    subscription_type: str | None = None


class RefreshedCredentialIn(ApiModel):
    """The rotated ``.credentials.json`` an agent read back after a CLI run."""

    credentials: str


class RefreshedCredentialOut(ApiModel):
    ok: bool = True
    #: False when the posted file was not strictly newer than the stored one.
    updated: bool = False


class UsageIn(ApiModel):
    model: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    cost_usd: float = 0.0
    duration_ms: int = 0
    action: str = ""
    external_ref: str = ""


class UsageBreakdownOut(ApiModel):
    input: int = 0
    output: int = 0
    cache_read: int = 0
    cache_write: int = 0


class UsageStatsOut(ApiModel):
    requests_today: int = 0
    avg_latency_ms: int = 0
    cost_month: float = 0.0
    week_tokens: int = 0
    week_resets_at: str = ""
    breakdown: UsageBreakdownOut = Field(default_factory=UsageBreakdownOut)


def _meta(payload: dict | None) -> CredentialMetaOut | None:
    return None if payload is None else CredentialMetaOut.model_validate(payload)


def _bad_request(exc: ClaudeCredentialsError) -> HTTPException:
    return HTTPException(status_code=400, detail=str(exc))


# ---------------------------------------------------------------- own
@router.get("", response_model=CredentialStatusOut)
def credential_status(
    user: User = Depends(require_user), db: Session = Depends(get_db)
) -> CredentialStatusOut:
    """Whether own/shared credentials exist and which one will be used.

    Metadata and booleans only — never the token.
    """
    payload = claude_credentials.status_for(db, user.id)
    return CredentialStatusOut(
        has_own=payload["hasOwn"],
        has_shared=payload["hasShared"],
        mode=payload["mode"],
        prefer_shared=payload["preferShared"],
        own=_meta(payload["own"]),
        shared=_meta(payload["shared"]),
    )


@router.put("", response_model=CredentialStatusOut)
def upload_own_credential(
    body: CredentialUpload,
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
) -> CredentialStatusOut:
    """Upload or replace the signed-in user's own credential."""
    try:
        claude_credentials.upsert_own(db, user.id, body.credentials, body.label)
    except ClaudeCredentialsError as exc:
        audit_service.record(
            category="credential",
            action="Rejected an invalid Claude credential upload",
            target="claude:own",
            status="warning",
            owner_id=user.id,
            db=db,
        )
        raise _bad_request(exc) from exc
    audit_service.record(
        category="credential",
        action="Uploaded a personal Claude credential",
        target="claude:own",
        owner_id=user.id,
        db=db,
    )
    return credential_status(user=user, db=db)


@router.delete("", response_model=OkResponse)
def delete_own_credential(
    user: User = Depends(require_user), db: Session = Depends(get_db)
) -> OkResponse:
    """Delete the signed-in user's own credential; they fall back to shared."""
    removed = claude_credentials.delete_own(db, user.id)
    if removed:
        audit_service.record(
            category="credential",
            action="Deleted their personal Claude credential",
            target="claude:own",
            owner_id=user.id,
            db=db,
        )
    return OkResponse()


@router.put("/mode", response_model=CredentialStatusOut)
def set_credential_mode(
    body: CredentialModeUpdate,
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
) -> CredentialStatusOut:
    """Run under ``"own"`` or the ``"shared"`` account, without deleting either."""
    try:
        claude_credentials.set_preferred_mode(db, user.id, body.mode)
    except ClaudeCredentialsError as exc:
        raise _bad_request(exc) from exc
    audit_service.record(
        category="credential",
        action=f"Switched Claude credential mode to {body.mode}",
        target="claude:mode",
        owner_id=user.id,
        db=db,
    )
    return credential_status(user=user, db=db)


# ---------------------------------------------------------------- shared
@router.put("/shared", response_model=CredentialStatusOut)
def upload_shared_credential(
    body: CredentialUpload,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> CredentialStatusOut:
    """Admin-only: upload or replace the workspace's shared credential."""
    try:
        claude_credentials.upsert_shared(db, body.credentials, body.label)
    except ClaudeCredentialsError as exc:
        raise _bad_request(exc) from exc
    audit_service.record(
        category="credential",
        action="Uploaded the shared Claude credential",
        target="claude:shared",
        owner_id=None,  # a shared-namespace event
        db=db,
    )
    return credential_status(user=admin, db=db)


@router.delete("/shared", response_model=OkResponse)
def delete_shared_credential(
    admin: User = Depends(require_admin),  # noqa: ARG001 - the gate is the point
    db: Session = Depends(get_db),
) -> OkResponse:
    """Admin-only: delete the shared credential."""
    removed = claude_credentials.delete_shared(db)
    if removed:
        audit_service.record(
            category="credential",
            action="Deleted the shared Claude credential",
            target="claude:shared",
            owner_id=None,
            db=db,
        )
    return OkResponse()


# ---------------------------------------------------------------- test
@router.post("/test", response_model=CredentialTestOut)
def test_credential(
    scope: str = Query(default="effective", pattern="^(effective|own|shared)$"),
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
) -> CredentialTestOut:
    """Check a stored credential is present, decryptable, parseable and unexpired.

    Not a liveness probe: the hub never calls Claude
    (:func:`app.services.claude_credentials.verify` explains the distinction).
    """
    return CredentialTestOut.model_validate(claude_credentials.verify(db, user.id, scope))


# ---------------------------------------------------------------- contract
@router.get("/resolve", response_model=ResolvedCredentialOut)
def resolve_credential(
    principal: User = Depends(require_credential_grant), db: Session = Depends(get_db)
) -> ResolvedCredentialOut:
    """**The one endpoint that returns credential material** (INTEGRATION.md §3/§4).

    Resolves own → shared → none for the calling principal and returns the
    decrypted ``.credentials.json``. Reachable with any *registered* audience,
    because the agent calls it with its own token.

    Every call is audited — success, miss and failure alike — which
    INTEGRATION.md §4 requires as a mitigation for the credential leaving the
    hub. The audit records who, from where and which credential; never the
    credential.
    """
    source_app = getattr(principal, "_aud", None)

    def _audit(action: str, status: str, target: str) -> None:
        audit_service.record(
            category="credential",
            action=action,
            actor=principal.email,
            actor_id=principal.id,
            actor_type="user",
            source=source_app,
            target=target,
            status=status,
            owner_id=principal.id,
            db=db,
        )

    try:
        resolved = claude_credentials.resolve_material(db, principal.id)
    except ClaudeCredentialsError as exc:
        _audit("Claude credential resolve failed", "error", "claude:resolve")
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    if resolved is None:
        _audit("Claude credential resolve found none", "warning", "claude:none")
        raise HTTPException(status_code=404, detail="No Claude credential is configured.")

    _audit(
        f"Resolved the {resolved['source']} Claude credential",
        "success",
        f"claude:{resolved['source']}",
    )
    return ResolvedCredentialOut(
        source=resolved["source"],
        credentials=resolved["credentials"],
        label=resolved["label"],
        status=resolved["status"],
        expires_at=resolved["expiresAt"],
        days_left=resolved["daysLeft"],
        scopes=resolved["scopes"],
        subscription_type=resolved["subscriptionType"],
    )


@router.put("/refreshed", response_model=RefreshedCredentialOut)
def persist_refreshed_credential(
    body: RefreshedCredentialIn,
    principal: User = Depends(require_credential_grant),
    db: Session = Depends(get_db),
) -> RefreshedCredentialOut:
    """Write back a token the Claude CLI rotated on the agent host.

    INTEGRATION.md §4: the CLI refreshes the access token in place, so unless
    the rotated file comes back the hub's copy goes stale and the credential
    eventually dies. Applies to the same row ``/resolve`` would have handed out,
    and only when the posted file is strictly newer — a logged-out or failed
    refresh can never clobber a good credential.
    """
    updated = claude_credentials.persist_refreshed_from_raw(
        db, principal.id, body.credentials
    )
    if updated:
        audit_service.record(
            category="credential",
            action="Captured a rotated Claude token",
            actor=principal.email,
            actor_id=principal.id,
            source=getattr(principal, "_aud", None),
            target="claude:refreshed",
            owner_id=principal.id,
            db=db,
        )
    return RefreshedCredentialOut(ok=True, updated=updated)


# ---------------------------------------------------------------- usage
@router.post("/usage", response_model=OkResponse, status_code=201)
def append_usage(
    body: UsageIn,
    principal: User = Depends(require_credential_grant),
    db: Session = Depends(get_db),
) -> OkResponse:
    """Append one completed Claude call's token/cost figures.

    Attribution comes from the token, never the body: ``owner_id`` is the
    principal and ``source`` is the caller's audience, so an agent cannot post
    spend against another user.
    """
    _row, credential_source = claude_credentials.resolve(db, principal.id)
    claude_usage.record(
        db,
        owner_id=principal.id,
        source=getattr(principal, "_aud", None) or "emehub",
        model=body.model,
        input_tokens=body.input_tokens,
        output_tokens=body.output_tokens,
        cache_read_tokens=body.cache_read_tokens,
        cache_write_tokens=body.cache_write_tokens,
        cost_usd=body.cost_usd,
        duration_ms=body.duration_ms,
        action=body.action,
        credential_source=credential_source,
        external_ref=body.external_ref,
    )
    return OkResponse()


@router.get("/usage", response_model=UsageStatsOut)
def usage_stats(
    user: User = Depends(require_user), db: Session = Depends(get_db)
) -> UsageStatsOut:
    """The signed-in user's own Claude spend, scoped by ``owned()``."""
    payload = claude_usage.stats(db, user)
    return UsageStatsOut(
        requests_today=payload["requestsToday"],
        avg_latency_ms=payload["avgLatencyMs"],
        cost_month=payload["costMonth"],
        week_tokens=payload["weekTokens"],
        week_resets_at=payload["weekResetsAt"],
        breakdown=UsageBreakdownOut(
            input=payload["breakdown"]["input"],
            output=payload["breakdown"]["output"],
            cache_read=payload["breakdown"]["cacheRead"],
            cache_write=payload["breakdown"]["cacheWrite"],
        ),
    )
