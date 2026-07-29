"""Per-call Claude usage records (tokens, cost, latency), ``owner_id``-scoped.

The hub does no domain work and never invokes Claude itself (CLAUDE.md › What
this repo is). It is, however, the only place that knows *whose* credential a
call ran under, so it is the natural place for the suite-wide spend ledger:
agents append one row per completed Claude CLI call and the hub aggregates them
per user.

``owner_id`` is the hub user the spend is attributed to. NULL means the call ran
with no attributable user — such rows land in the shared namespace and are
therefore visible to everyone (:mod:`app.services.ownership`), which is the
intended behaviour for unattributed shared-account spend.

Nothing here is secret: a usage row records *how much* a call cost, never the
credential it ran under.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base, UTCDateTime, utcnow


class ClaudeUsage(Base):
    __tablename__ = "claude_usage"

    id: Mapped[int] = mapped_column(primary_key=True)
    ts: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, index=True)
    # Which application reported the call — taken from the caller's token
    # audience, never from the request body.
    source: Mapped[str] = mapped_column(String(32), default="emehub", index=True)
    # The agent-side correlation id (a QAgent run, a DAgent execution). Opaque
    # to the hub — it never joins on it.
    external_ref: Mapped[str] = mapped_column(String(120), default="", index=True)
    model: Mapped[str] = mapped_column(String(64), default="")
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cache_read_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cache_write_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    duration_ms: Mapped[int] = mapped_column(Integer, default=0)
    action: Mapped[str] = mapped_column(String(120), default="")
    # Which credential the call ran under: "own" | "shared".
    credential_source: Mapped[str] = mapped_column(String(16), default="")
    # Workspace scoping: NULL == the shared namespace.
    owner_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
