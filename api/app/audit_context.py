"""Per-request audit attribution.

The authenticated principal for the current request is stashed in ContextVars so
``audit_service.record`` can attribute an event to a real person and a real
application without every call site threading them through.

:func:`bind_audit_actor` is a FastAPI dependency attached to every router at
registration. It runs inside the endpoint's request context — unlike a
``BaseHTTPMiddleware``, which runs in a different context and would silently
lose the value.

It never authenticates anything: a request reaches an endpoint only after
``require_user`` (or the guard) has already accepted it. This is attribution
metadata, not a security boundary.
"""

from __future__ import annotations

from contextvars import ContextVar

from fastapi import Request

from app.config import AUDIENCE_HUB
from app.services import auth_service

_actor: ContextVar[str | None] = ContextVar("audit_actor", default=None)
_actor_id: ContextVar[int | None] = ContextVar("audit_actor_id", default=None)
_source: ContextVar[str] = ContextVar("audit_source", default=AUDIENCE_HUB)
_ip: ContextVar[str] = ContextVar("audit_ip", default="")


def set_actor(label: str | None, actor_id: int | None = None) -> None:
    _actor.set(label)
    _actor_id.set(actor_id)


def get_actor() -> str | None:
    return _actor.get()


def get_actor_id() -> int | None:
    return _actor_id.get()


def set_source(source: str) -> None:
    _source.set(source)


def get_source() -> str:
    return _source.get()


def set_ip(ip: str) -> None:
    _ip.set(ip)


def get_ip() -> str:
    return _ip.get()


def reset() -> None:
    """Clear the ambient context (used by tests)."""
    set_actor(None, None)
    _source.set(AUDIENCE_HUB)
    _ip.set("")


async def bind_audit_actor(request: Request) -> None:
    """Record who — and which application — is behind this request."""
    reset()
    set_ip(request.client.host if request.client else "")
    header = request.headers.get("authorization", "")
    if not header.lower().startswith("bearer "):
        return
    try:
        claims = auth_service.decode_access_token(header[7:].strip())
    except Exception:  # noqa: BLE001 - attribution must never break a request
        return
    label = (claims.get("email") or "").strip()
    try:
        actor_id = int(claims.get("sub") or 0) or None
    except (TypeError, ValueError):
        actor_id = None
    set_actor(label or None, actor_id)
    set_source(claims.get("aud") or AUDIENCE_HUB)
