"""Cached provider metadata for the query builder's pickers.

Reading a project's work-item types, states, area and iteration trees, members and
tags is several round trips to the provider, each spending the connection's PAT.
Doing that every time a filter panel opens is slow and rude, so the payload is
cached per connection with a TTL (``EMEHUB_METADATA_TTL_MINUTES``).

A table rather than a process-local dict, because an in-process cache diverges
across uvicorn workers: two requests hit two workers and get two different
"fields read 4 minutes ago" answers, and a refresh warms only the worker that
served it.

``payload`` is opaque JSON on purpose — the shape belongs to the adapter and
differs per provider, so modelling columns would mean a migration every time a
picker gains a field. Nothing reads it but the code that wrote it, and a payload it
cannot parse is simply a miss. No secrets: names, paths and display names, the same
things the metadata endpoint already returns to the browser.

``fetched_at`` is when the provider was really read, **not** when the row was last
touched — a failed refresh leaves it alone so the reported age stays true.

``ON DELETE CASCADE``: deleting a connection must not strand its cache, and the
cache is worthless without the credential it was read with.

Revision ID: 0008_metadata_cache
Revises: 0007_knowledge_progress
Create Date: 2026-08-06
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op
from app.db import UTCDateTime

revision: str = "0008_metadata_cache"
down_revision: str | None = "0007_knowledge_progress"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "provider_metadata_cache",
        sa.Column(
            "connection_id",
            sa.Integer(),
            sa.ForeignKey("provider_connections.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("payload", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("fetched_at", UTCDateTime(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("provider_metadata_cache")
