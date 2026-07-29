"""Ticket store: the ``tickets`` table (Phase 4).

A normalised mirror of provider work items, served to agents through
``GET /tickets`` and ``GET /tickets/{external_id}`` (INTEGRATION.md §3).

**On ``connection_id``.** It references ``provider_connections.id`` in intent but
is created here as a plain indexed integer with no ``REFERENCES`` clause. That
table is created by the connections slice, which is being built in parallel, and
Postgres refuses to create a constraint against a table that does not exist yet.
The column carries the same values either way; adding the constraint is a
one-line ``op.create_foreign_key`` in a later migration, once both slices have
landed.

Revision ID: 0002_tickets
Revises: 0001_identity
Create Date: 2026-07-29
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from app.db import UTCDateTime

revision: str = "0002_tickets"
down_revision: str | None = "0001_identity"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "tickets",
        sa.Column("id", sa.Integer(), primary_key=True),
        # The provider's own identifier, e.g. "SUR-1428".
        sa.Column("external_id", sa.String(length=64), nullable=False),
        sa.Column("provider_kind", sa.String(length=16), nullable=False, server_default=""),
        sa.Column("project_id", sa.Integer(), nullable=True),
        # See the module docstring: no FK constraint yet, by design.
        sa.Column("connection_id", sa.Integer(), nullable=True),
        sa.Column("title", sa.String(length=500), nullable=False, server_default=""),
        sa.Column(
            "work_item_type",
            sa.String(length=32),
            nullable=False,
            server_default="User Story",
        ),
        sa.Column("status", sa.String(length=32), nullable=False, server_default=""),
        sa.Column("priority", sa.String(length=16), nullable=False, server_default="Medium"),
        sa.Column("assignee", sa.String(length=120), nullable=False, server_default=""),
        sa.Column("sprint", sa.String(length=120), nullable=False, server_default=""),
        sa.Column("area_path", sa.String(length=300), nullable=False, server_default=""),
        sa.Column("epic", sa.String(length=300), nullable=False, server_default=""),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        # sa.JSON, not JSONB: migrations stay portable so the test suite runs the
        # same schema on SQLite.
        sa.Column("labels", sa.JSON(), nullable=True),
        sa.Column("acceptance_criteria", sa.JSON(), nullable=True),
        sa.Column("acceptance_criteria_html", sa.Text(), nullable=False, server_default=""),
        sa.Column("comments", sa.JSON(), nullable=True),
        sa.Column("attachments", sa.JSON(), nullable=True),
        sa.Column("linked_prs", sa.JSON(), nullable=True),
        sa.Column("synced_at", UTCDateTime(), nullable=True),
        # Workspace scoping: NULL == the shared namespace (services/ownership.py).
        sa.Column(
            "owner_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index("ix_tickets_external_id", "tickets", ["external_id"])
    op.create_index("ix_tickets_provider_kind", "tickets", ["provider_kind"])
    op.create_index("ix_tickets_project_id", "tickets", ["project_id"])
    op.create_index("ix_tickets_connection_id", "tickets", ["connection_id"])
    op.create_index("ix_tickets_owner_id", "tickets", ["owner_id"])
    # The upsert key: a re-sync of the same work item must find its existing row.
    op.create_index(
        "ix_tickets_owner_provider_external",
        "tickets",
        ["owner_id", "provider_kind", "external_id"],
    )


def downgrade() -> None:
    op.drop_table("tickets")
