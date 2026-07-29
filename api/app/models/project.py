"""Project registry — the stable identity every other project table joins on.

Ported from QAgent's ``models/project.py`` but deliberately **reduced**. QAgent's
row is a *discovered* provider project: ``provider_kind`` + ``external_id``
pulled from an ADO/Jira connection during ``POST /projects/refresh``. Discovery
needs a provider PAT, and provider PATs never leave the hub only because the hub
never hands them out — the agent that holds the connection does the discovery.
So the hub's row is just the **registry entry**:

* ``key``  — the identifier ``project_config.key`` and
  ``project_knowledge.project_key`` both point at. Human-authored, stable.
* ``name`` — display label.

``owner_id`` is the workspace scoping column (nullable FK to ``users.id``; NULL
means the workspace-wide shared namespace) — the convention every scoped table
in the hub follows (``app.services.ownership``). Uniqueness is therefore scoped
to ``(key, owner_id)``: the same project key may exist once per member and once
in the shared namespace, exactly as it does in QAgent under ADR 0009 §3.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base, timestamp_column, utcnow


class Project(Base):
    __tablename__ = "projects"
    __table_args__ = (UniqueConstraint("key", "owner_id", name="uq_projects_key_owner"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(String(200), index=True)
    name: Mapped[str] = mapped_column(String(200), default="")

    created_at: Mapped[datetime] = timestamp_column()
    updated_at: Mapped[datetime] = timestamp_column(onupdate=utcnow)
    # Workspace scoping: NULL == shared. See app.services.ownership.
    owner_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True
    )
