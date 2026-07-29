"""Session model — one row per active login (device/browser).

The row id **is** the ``sid`` embedded in every access token, so revoking the
session kills the user's access in every agent as their tokens expire
(INTEGRATION.md §2 › Session revocation).

Only the **sha256 hash** of the refresh token is stored. The plaintext exists in
exactly one place: the HttpOnly refresh cookie in the user's browser. A database
dump therefore contains no usable refresh token.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base, UTCDateTime, timestamp_column, utcnow


class Session(Base):
    __tablename__ = "auth_sessions"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)  # uuid4().hex == sid
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    refresh_token_hash: Mapped[str] = mapped_column(String(64), default="")  # sha256 hex
    user_agent: Mapped[str] = mapped_column(String(400), default="")
    ip: Mapped[str] = mapped_column(String(64), default="")
    created_at: Mapped[datetime] = timestamp_column()
    last_seen_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime)
    revoked_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
