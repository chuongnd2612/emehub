"""Claude credentials and per-call usage (Phase 3 — Credentials).

``claude_credentials`` holds one encrypted ``.credentials.json`` per user plus
one shared row (``owner_id IS NULL``); ``claude_usage`` is the per-call
token/cost ledger. Both follow the workspace-scoping convention: a nullable
``owner_id`` FK where NULL means the shared namespace.

Portable across Postgres and SQLite (no JSONB) — the test suite builds its
schema by running these migrations.

Revision ID: 0002_claude_credentials
Revises: 0001_identity
Create Date: 2026-07-29
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

from app.db import UTCDateTime

revision: str = "0004_claude_credentials"
down_revision: str | None = "0003_projects"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "claude_credentials",
        sa.Column("id", sa.Integer(), primary_key=True),
        # NULL == the single shared credential. Unique so a user cannot end up
        # with two rows; NULLs stay distinct in both dialects, so the shared
        # singleton is enforced by the service's upsert instead.
        sa.Column(
            "owner_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=True,
        ),
        # `enc::v1:` envelope over the raw file contents — never plaintext.
        sa.Column("credentials", sa.Text(), nullable=False, server_default=""),
        sa.Column("label", sa.String(length=120), nullable=False, server_default=""),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="active"),
        # Metadata parsed from the upload. Never the token.
        sa.Column("expires_at", UTCDateTime(), nullable=True),
        sa.Column("scopes", sa.JSON(), nullable=True),
        sa.Column("subscription_type", sa.String(length=64), nullable=True),
        sa.Column(
            "prefer_shared", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
        sa.Column("created_at", UTCDateTime(), nullable=True),
        sa.Column("updated_at", UTCDateTime(), nullable=True),
    )
    op.create_index(
        "ix_claude_credentials_owner_id", "claude_credentials", ["owner_id"], unique=True
    )

    op.create_table(
        "claude_usage",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("ts", UTCDateTime(), nullable=True),
        # The audience that reported the call — from the token, not the body.
        sa.Column("source", sa.String(length=32), nullable=False, server_default="emehub"),
        sa.Column("external_ref", sa.String(length=120), nullable=False, server_default=""),
        sa.Column("model", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("input_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("output_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("cache_read_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("cache_write_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("cost_usd", sa.Float(), nullable=False, server_default="0"),
        sa.Column("duration_ms", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("action", sa.String(length=120), nullable=False, server_default=""),
        sa.Column(
            "credential_source", sa.String(length=16), nullable=False, server_default=""
        ),
        sa.Column(
            "owner_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index("ix_claude_usage_ts", "claude_usage", ["ts"])
    op.create_index("ix_claude_usage_source", "claude_usage", ["source"])
    op.create_index("ix_claude_usage_external_ref", "claude_usage", ["external_ref"])
    op.create_index("ix_claude_usage_owner_id", "claude_usage", ["owner_id"])


def downgrade() -> None:
    op.drop_table("claude_usage")
    op.drop_index("ix_claude_credentials_owner_id", table_name="claude_credentials")
    op.drop_table("claude_credentials")
