"""User model — an authenticated account. The hub is the source of truth for
identity across the suite ([ADR 0001](../../../docs/adr/0001-emehub-is-the-source-of-truth.md)).

``email`` is stored lowercased and is unique. ``password_hash`` holds an argon2
hash — plaintext passwords are never stored, logged or returned. ``role`` is
``"admin"`` or ``"member"``; agents authorise from that claim (INTEGRATION.md §1).

The first account is seeded from ``EMEHUB_ADMIN_EMAIL`` / ``EMEHUB_ADMIN_PASSWORD``;
subsequent ones are created or invited by an admin through ``/auth/users``.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base, UTCDateTime, timestamp_column, utcnow

ROLE_ADMIN = "admin"
ROLE_MEMBER = "member"
USER_ROLES = (ROLE_ADMIN, ROLE_MEMBER)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)  # lowercased
    first_name: Mapped[str] = mapped_column(String(120), default="")
    last_name: Mapped[str] = mapped_column(String(120), default="")
    role: Mapped[str] = mapped_column(String(16), default=ROLE_MEMBER)
    password_hash: Mapped[str] = mapped_column(String(255), default="")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    # TOTP shared secret, base32. Stored as-is so QAgent's existing secrets can
    # migrate opaquely (ROADMAP Phase 2 › Data migration). Never returned by any
    # endpoint except the one-shot /auth/2fa/setup response.
    totp_secret: Mapped[str | None] = mapped_column(String(64), nullable=True)
    totp_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = timestamp_column()
    updated_at: Mapped[datetime] = timestamp_column(onupdate=utcnow)
    # Stamped on successful login and token refresh; never backfilled.
    last_active: Mapped[datetime | None] = mapped_column(
        UTCDateTime, nullable=True, default=None
    )

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}".strip()
