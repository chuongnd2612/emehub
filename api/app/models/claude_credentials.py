"""Claude CLI credential — one row per user, plus one shared row.

The Claude CLI reads its OAuth session from ``<CLAUDE_CONFIG_DIR>/.credentials.json``.
Rather than every host sharing one machine-wide login, each row here holds the
**encrypted** contents of one user's (or the shared/admin) credentials file, so
an agent can fetch the credential it should run with from
``GET /credentials/claude/resolve`` and materialise it into a private config dir
(INTEGRATION.md §4 — the one documented secret that leaves the hub).

``owner_id`` NULL identifies the single **shared** credential, following the
workspace-scoping convention every table in the hub uses
(:mod:`app.services.ownership`): NULL is the shared namespace, a value is
private to that user. There is at most one row per non-null ``owner_id`` and at
most one shared row; both are enforced by the service layer's upsert, plus a
unique index on ``owner_id`` for the owned rows.

**Nothing on this model is safe to log or return except the parsed metadata.**
``credentials`` is an ``enc::v1:`` envelope (:mod:`app.crypto`) around the raw
file contents, which include the access *and* refresh token. Only
:func:`app.services.claude_credentials.resolve_material` ever decrypts it, and
only ``GET /credentials/claude/resolve`` ever returns the result.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, Boolean, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base, UTCDateTime, timestamp_column, utcnow

#: Persisted status. Only these two are ever stored.
STATUS_ACTIVE = "active"
#: Set when a real CLI call reported the token is no longer usable, or when the
#: parsed ``expiresAt`` has passed.
STATUS_EXPIRED = "expired"

#: Derived only — never stored. Mirrors the frontend's rule in
#: ``app/src/data/credentials.ts`` (``daysLeft <= 2``) so the hub and the SPA
#: agree on what "about to lapse" means.
STATUS_EXPIRING = "expiring"

STORED_STATUSES = (STATUS_ACTIVE, STATUS_EXPIRED)


class ClaudeCredentials(Base):
    __tablename__ = "claude_credentials"

    id: Mapped[int] = mapped_column(primary_key=True)
    # NULL = the shared credential. Same ownership FK shape as every other
    # scoped table rather than a bespoke "is_shared" flag.
    owner_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True, unique=True
    )
    # enc::v1: envelope over the raw `.credentials.json` contents (app.crypto).
    credentials: Mapped[str] = mapped_column(Text, default="")
    label: Mapped[str] = mapped_column(String(120), default="")
    status: Mapped[str] = mapped_column(String(16), default=STATUS_ACTIVE)
    # Metadata parsed from the uploaded file — all optional, never the token.
    expires_at: Mapped[datetime | None] = mapped_column(
        UTCDateTime, nullable=True, default=None
    )
    scopes: Mapped[list | None] = mapped_column(JSON, nullable=True, default=None)
    subscription_type: Mapped[str | None] = mapped_column(
        String(64), nullable=True, default=None
    )
    # Own-row only: the user has their own credential on file but wants to run
    # under the shared account. Lets them switch back and forth without
    # deleting the upload. Always False on the shared row.
    prefer_shared: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = timestamp_column()
    updated_at: Mapped[datetime] = timestamp_column(onupdate=utcnow)
