"""Which Claude model a user's agent runs should use.

## Why this is a row and not configuration

``settings.claude_model`` is one value, set at deploy time, identical for
everybody. Which model a member wants their work run with is a per-person choice
they change whenever they like, so it is a row, and it takes effect on the next
build rather than the next deploy.

## It decides something

This is not a display setting. The hub's own knowledge builds resolve their
model and effort through :mod:`app.services.model_preferences`, keyed on the
owner of the row being built — so picking a model here changes what the next
build actually runs on.

## Absent means "the system defaults"

Nothing is seeded. A user with no row gets the defaults from
:mod:`app.config`, and the first save is what creates the row — so a fresh
install works with an empty table, and clearing the table is a reset rather than
an outage.

## Nothing here is secret

A model id is a public string. This table carries no credential, no token and no
attribution to any account beyond the owning user.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base, timestamp_column, utcnow


class UserModelPreferences(Base):
    __tablename__ = "user_model_preferences"

    #: The owning user, and the primary key: one row per person, at most.
    #: ``CASCADE`` because a preference has no meaning without its account —
    #: unlike an audit or usage record, there is nothing here to outlive it.
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    #: Model id (``claude-opus-5``, …), never a display label. The validated set
    #: lives in :mod:`app.services.model_preferences`. Empty means "not chosen".
    main_model: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    #: Claude CLI ``--effort`` level. Empty means "not chosen" — same convention
    #: as the model column, so one absent-means-default rule covers the row.
    effort: Mapped[str] = mapped_column(String(16), default="", nullable=False)
    updated_at: Mapped[datetime] = timestamp_column(onupdate=utcnow)
