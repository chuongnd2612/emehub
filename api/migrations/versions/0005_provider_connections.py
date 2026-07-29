"""Provider connections: named Azure DevOps / GitHub / Jira accounts.

Phase 3 — Credentials. The PAT lives in one nullable ``pat_encrypted`` column
and nowhere else, so "the PAT never leaves the hub" is a property you can check
by reading the schema.

``sa.JSON``, not ``JSONB``: migrations stay dialect-portable so the test suite
runs the real migrations on SQLite (app/db.py).

Revision ID: 0002_provider_connections
Revises: 0001_identity
Create Date: 2026-07-29
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

from app.db import UTCDateTime

revision: str = "0005_provider_connections"
down_revision: str | None = "0004_claude_credentials"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "provider_connections",
        sa.Column("id", sa.Integer(), primary_key=True),
        # azure_devops | github | jira. Not unique — a kind holds many accounts.
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("label", sa.String(length=160), nullable=False, server_default=""),
        # ADO org URL / Jira site / GitHub Enterprise API base.
        sa.Column("base_url", sa.String(length=500), nullable=False, server_default=""),
        # Non-secret adapter fields only; credential-shaped keys are refused on write.
        sa.Column("config", sa.JSON(), nullable=False, server_default="{}"),
        # The only secret in this table — always an `enc::v1:` envelope (app/crypto.py).
        sa.Column("pat_encrypted", sa.Text(), nullable=True),
        # ["work_item"], ["repository"] or both.
        sa.Column("capabilities", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("connected", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("last_sync", UTCDateTime(), nullable=True),
        sa.Column("last_tested_at", UTCDateTime(), nullable=True),
        sa.Column("created_at", UTCDateTime(), nullable=True),
        sa.Column("updated_at", UTCDateTime(), nullable=True),
        # Workspace scoping: NULL == the shared namespace (services/ownership.py).
        # CASCADE, unlike audit_logs' SET NULL: orphaning a private connection
        # into the shared namespace when its owner is deleted would silently
        # publish their credential to the whole workspace.
        sa.Column(
            "owner_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=True,
        ),
    )
    op.create_index("ix_provider_connections_kind", "provider_connections", ["kind"])
    op.create_index("ix_provider_connections_owner_id", "provider_connections", ["owner_id"])


def downgrade() -> None:
    op.drop_index("ix_provider_connections_owner_id", table_name="provider_connections")
    op.drop_index("ix_provider_connections_kind", table_name="provider_connections")
    op.drop_table("provider_connections")
