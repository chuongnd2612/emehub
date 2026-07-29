"""Identity and audit: users, auth_sessions, audit_logs.

The hub's baseline schema (Phase 2 — Identity).

Revision ID: 0001_identity
Revises:
Create Date: 2026-07-29
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

from app.db import UTCDateTime

revision: str = "0001_identity"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True),
        # Stored lowercased; unique across the workspace.
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("first_name", sa.String(length=120), nullable=False, server_default=""),
        sa.Column("last_name", sa.String(length=120), nullable=False, server_default=""),
        sa.Column("role", sa.String(length=16), nullable=False, server_default="member"),
        # argon2 hash — never a plaintext password.
        sa.Column("password_hash", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("totp_secret", sa.String(length=64), nullable=True),
        sa.Column("totp_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", UTCDateTime(), nullable=True),
        sa.Column("updated_at", UTCDateTime(), nullable=True),
        sa.Column("last_active", UTCDateTime(), nullable=True),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)

    op.create_table(
        "auth_sessions",
        # The primary key IS the `sid` claim carried by every access token.
        sa.Column("id", sa.String(length=32), primary_key=True),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        # sha256 hex of the opaque refresh token. The plaintext is never stored.
        sa.Column(
            "refresh_token_hash", sa.String(length=64), nullable=False, server_default=""
        ),
        sa.Column("user_agent", sa.String(length=400), nullable=False, server_default=""),
        sa.Column("ip", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("created_at", UTCDateTime(), nullable=True),
        sa.Column("last_seen_at", UTCDateTime(), nullable=True),
        sa.Column("expires_at", UTCDateTime(), nullable=False),
        sa.Column("revoked_at", UTCDateTime(), nullable=True),
    )
    op.create_index("ix_auth_sessions_user_id", "auth_sessions", ["user_id"])
    op.create_index(
        "ix_auth_sessions_refresh_token_hash", "auth_sessions", ["refresh_token_hash"]
    )

    op.create_table(
        "audit_logs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("ts", UTCDateTime(), nullable=True),
        sa.Column("category", sa.String(length=32), nullable=False, server_default="auth"),
        # The audience that appended the event: emehub | qagent | dagent.
        sa.Column("source", sa.String(length=32), nullable=False, server_default="emehub"),
        sa.Column("actor", sa.String(length=200), nullable=False, server_default="system"),
        sa.Column("actor_type", sa.String(length=16), nullable=False, server_default="user"),
        sa.Column(
            "actor_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("action", sa.String(length=200), nullable=False, server_default=""),
        sa.Column("target", sa.String(length=400), nullable=False, server_default=""),
        sa.Column("ip", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="success"),
        sa.Column("meta", sa.Text(), nullable=False, server_default=""),
        # sa.JSON, not JSONB: migrations stay portable so the test suite can run
        # the same schema on SQLite.
        sa.Column("detail", sa.JSON(), nullable=True),
        # Workspace scoping: NULL == the shared namespace (services/ownership.py).
        sa.Column(
            "owner_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index("ix_audit_logs_ts", "audit_logs", ["ts"])
    op.create_index("ix_audit_logs_category", "audit_logs", ["category"])
    op.create_index("ix_audit_logs_source", "audit_logs", ["source"])
    op.create_index("ix_audit_logs_actor_type", "audit_logs", ["actor_type"])
    op.create_index("ix_audit_logs_actor_id", "audit_logs", ["actor_id"])
    op.create_index("ix_audit_logs_owner_id", "audit_logs", ["owner_id"])


def downgrade() -> None:
    op.drop_table("audit_logs")
    op.drop_table("auth_sessions")
    op.drop_index("ix_users_email", table_name="users")
    op.drop_table("users")
