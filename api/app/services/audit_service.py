"""Audit trail — append-only, best-effort, never in the way.

:func:`record` writes one row on its own short-lived session and swallows any
failure: auditing must never break the action being audited. It fills the actor,
actor id, source application and client IP from the ambient request context
(:mod:`app.audit_context`) unless the caller overrides them.

Agents append their own events through ``POST /audit/events`` (INTEGRATION.md
§3). The ``source`` of such an event is taken from the caller's token audience,
never from the request body — an agent cannot claim to be the hub.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from app import audit_context
from app import db as db_module
from app.db import utcnow
from app.logging import logger
from app.models.audit import AuditLog
from app.services.ownership import owned


def record(
    *,
    category: str,
    action: str,
    actor_type: str = "user",
    actor: str | None = None,
    actor_id: int | None = None,
    source: str | None = None,
    target: str = "",
    status: str = "success",
    ip: str | None = None,
    meta: str = "",
    detail: dict | None = None,
    owner_id: int | None = None,
    ts: datetime | None = None,
    db: Session | None = None,
) -> None:
    """Append one audit event. Best-effort — never raises.

    Args:
        category: one of :data:`app.models.audit.AUDIT_CATEGORIES`.
        action: human-readable, e.g. ``"Signed in"``.
        actor_type: ``user`` | ``agent`` | ``system``.
        source: the application appending the event; defaults to the calling
            token's audience.
        db: write on this session instead of a fresh one (used by tests and by
            handlers that need the row visible inside their own transaction).
    """
    row = AuditLog(
        ts=ts or utcnow(),
        category=category,
        source=source or audit_context.get_source(),
        actor=actor if actor is not None else (audit_context.get_actor() or _default_actor(actor_type)),
        actor_type=actor_type,
        actor_id=actor_id if actor_id is not None else audit_context.get_actor_id(),
        action=action,
        target=target,
        ip=ip if ip is not None else audit_context.get_ip(),
        status=status,
        meta=meta,
        detail=detail,
        owner_id=owner_id,
    )
    try:
        if db is not None:
            db.add(row)
            db.commit()
            return
        session = db_module.SessionLocal()
        try:
            session.add(row)
            session.commit()
        finally:
            session.close()
    except Exception as exc:  # noqa: BLE001 - auditing must never break the caller
        logger.warning("audit record failed (%s / %s): %s", category, action, exc)


def _default_actor(actor_type: str) -> str:
    return {"agent": "agent", "system": "system"}.get(actor_type, "unknown")


def list_events(
    db: Session,
    user,  # app.models.user.User | None
    *,
    category: str | None = None,
    source: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[AuditLog]:
    """Events visible to ``user`` (their own + the shared namespace), newest first."""
    query = owned(db.query(AuditLog), AuditLog, user)
    if category:
        query = query.filter(AuditLog.category == category)
    if source:
        query = query.filter(AuditLog.source == source)
    return (
        query.order_by(AuditLog.ts.desc(), AuditLog.id.desc())
        .offset(max(offset, 0))
        .limit(max(1, min(limit, 500)))
        .all()
    )
