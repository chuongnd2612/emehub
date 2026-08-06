"""Saved ticket queries, and the shipped presets.

Named clause queries, scoped the way everything else in this hub is scoped:
``owner_id`` nullable, NULL meaning the shared namespace (`ownership.py`).

``destination`` is a column because a query is **not** portable across providers —
one naming ``areaPath`` cannot run on Jira, ``parentId`` has no column in the
mirror. Without recording it, the list would offer a query guaranteed to be refused
the moment it was applied.

Shipped presets live in this same table, told apart by ``built_in``: one list, one
shape. Seeding is done by the service on read rather than in this migration, so a
preset can be corrected in code without a data migration chasing it.

The unique constraint is ``(owner_id, destination, name)``. Postgres treats NULLs as
distinct in a unique index, which is what lets one shared name coexist with each
member's own.

Revision ID: 0009_saved_queries
Revises: 0008_metadata_cache
Create Date: 2026-08-06
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op
from app.db import UTCDateTime

revision: str = "0009_saved_queries"
down_revision: str | None = "0008_metadata_cache"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "saved_ticket_queries",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("destination", sa.String(length=32), nullable=False, index=True),
        sa.Column("query", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("description", sa.String(length=400), nullable=False, server_default=""),
        sa.Column("built_in", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "owner_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=True,
            index=True,
        ),
        sa.Column("created_at", UTCDateTime(), nullable=False),
        sa.Column("updated_at", UTCDateTime(), nullable=False),
        sa.UniqueConstraint("owner_id", "destination", "name", name="uq_saved_query_name"),
    )


def downgrade() -> None:
    op.drop_table("saved_ticket_queries")
