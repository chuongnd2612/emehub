"""AuditLog model — append-only trail of everything that mattered.

Rows are written by ``services.audit_service.record`` and never updated or
deleted in normal use. Two things differ from QAgent's table, both because the
hub serves more than one application:

* ``source`` — the audience that produced the event (``emehub`` | ``qagent`` |
  ``dagent``), so an agent can append attributed events through
  ``POST /audit/events`` (INTEGRATION.md §3) without pretending to be the hub.
* ``actor_id`` — the hub user id behind the event, kept alongside the display
  label so the trail survives a rename.

``owner_id`` is the workspace scoping column (a nullable FK to ``users.id``;
NULL means the workspace-wide shared namespace) — the same convention every
scoped table in the hub follows.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base, timestamp_column

# Category buckets the Activity / Audit surfaces filter by.
AUDIT_CATEGORIES = (
    "auth",
    "identity",
    "credential",
    "connection",
    "project",
    "knowledge",
    "ticket",
    "settings",
    "agent",
)
AUDIT_ACTOR_TYPES = ("user", "agent", "system")
AUDIT_STATUSES = ("success", "warning", "error")


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    ts: Mapped[datetime] = timestamp_column(index=True)
    category: Mapped[str] = mapped_column(String(32), default="auth", index=True)
    # Which application appended the event — the token's `aud`.
    source: Mapped[str] = mapped_column(String(32), default="emehub", index=True)
    actor: Mapped[str] = mapped_column(String(200), default="system")
    actor_type: Mapped[str] = mapped_column(String(16), default="user", index=True)
    actor_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    action: Mapped[str] = mapped_column(String(200), default="")
    target: Mapped[str] = mapped_column(String(400), default="")
    ip: Mapped[str] = mapped_column(String(64), default="")
    status: Mapped[str] = mapped_column(String(16), default="success")
    meta: Mapped[str] = mapped_column(Text, default="")
    detail: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    # Workspace scoping: NULL == shared. See app.services.ownership.
    owner_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
