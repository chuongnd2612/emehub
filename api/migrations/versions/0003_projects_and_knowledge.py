"""Projects, project configuration and project knowledge.

Phase 4's metadata tables. The hub owns the *records*; repo clones, workspace
directories and knowledge artifacts stay on the agent host (ROADMAP.md Phase 4).

## The two connection columns are NOT foreign keys — deliberately

``project_config.work_item_connection_id`` / ``repository_connection_id``
reference ``provider_connections``, which is created by the connections slice
landing in parallel. Declaring the constraint here would couple this migration
to that one's revision order for no benefit, and would break the test suite
outright: SQLite accepts ``CREATE TABLE`` naming a missing parent, then fails
every ``INSERT`` with "no such table: main.provider_connections" once
``PRAGMA foreign_keys=ON`` (which ``app.db`` sets on every connection).

So the columns ship as plain nullable integers. The connections slice can add
the constraint in its own migration, once the parent table exists, with a
``batch_alter_table`` (SQLite cannot ``ADD CONSTRAINT`` in place). Nothing in
``app/models/project_config.py`` or ``app/services/`` imports that slice.

Revision ID: 0002_projects
Revises: 0001_identity
Create Date: 2026-07-29
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

from app.db import UTCDateTime

revision: str = "0003_projects"
down_revision: str | None = "0002_tickets"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ---------------------------------------------------------------- projects
    op.create_table(
        "projects",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("key", sa.String(length=200), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False, server_default=""),
        sa.Column("created_at", UTCDateTime(), nullable=True),
        sa.Column("updated_at", UTCDateTime(), nullable=True),
        # Workspace scoping: NULL == the shared namespace (services/ownership.py).
        sa.Column(
            "owner_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=True,
        ),
        # One key per namespace: a member's project and the shared one may share
        # a key; two members' may not collide with each other's.
        sa.UniqueConstraint("key", "owner_id", name="uq_projects_key_owner"),
    )
    op.create_index("ix_projects_key", "projects", ["key"])
    op.create_index("ix_projects_owner_id", "projects", ["owner_id"])

    # ---------------------------------------------------------- project_config
    op.create_table(
        "project_config",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("key", sa.String(length=200), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False, server_default=""),
        # See the module docstring: plain integers, no FK, on purpose.
        sa.Column("work_item_connection_id", sa.Integer(), nullable=True),
        sa.Column("repository_connection_id", sa.Integer(), nullable=True),
        sa.Column("base_url", sa.String(length=500), nullable=False, server_default=""),
        # sa.JSON, not JSONB — migrations stay portable so the suite runs on SQLite.
        sa.Column("repos", sa.JSON(), nullable=True),
        sa.Column("environments", sa.JSON(), nullable=True),
        # Passwords inside are `enc::v1:` envelopes (app/crypto.py), never plaintext.
        sa.Column("test_accounts", sa.JSON(), nullable=True),
        sa.Column("extra", sa.JSON(), nullable=True),
        sa.Column("manual_auth", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", UTCDateTime(), nullable=True),
        sa.Column("updated_at", UTCDateTime(), nullable=True),
        sa.Column(
            "owner_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.UniqueConstraint("key", "owner_id", name="uq_project_config_key_owner"),
    )
    op.create_index("ix_project_config_key", "project_config", ["key"])
    op.create_index("ix_project_config_owner_id", "project_config", ["owner_id"])

    # ------------------------------------------------------- project_knowledge
    op.create_table(
        "project_knowledge",
        sa.Column("id", sa.Integer(), primary_key=True),
        # compose_key(project_key, repo) == "<project>::<repo>", or "<project>".
        sa.Column("key", sa.String(length=320), nullable=False),
        sa.Column("project_key", sa.String(length=200), nullable=False, server_default=""),
        sa.Column("name", sa.String(length=200), nullable=False, server_default=""),
        sa.Column("provider", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("repo", sa.String(length=300), nullable=False, server_default=""),
        sa.Column("framework", sa.String(length=64), nullable=False, server_default="Playwright"),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="not_indexed"),
        sa.Column("confidence", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("version", sa.String(length=16), nullable=False, server_default="v1"),
        sa.Column("needs_refresh", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("last_indexed", UTCDateTime(), nullable=True),
        sa.Column("knowledge", sa.JSON(), nullable=True),
        # Agent-host directory holding knowledge.md/.json. Opaque to the hub.
        sa.Column("doc_path", sa.String(length=600), nullable=False, server_default=""),
        sa.Column("last_error", sa.String(length=1000), nullable=False, server_default=""),
        sa.Column("created_at", UTCDateTime(), nullable=True),
        sa.Column("updated_at", UTCDateTime(), nullable=True),
        sa.Column(
            "owner_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.UniqueConstraint("key", "owner_id", name="uq_project_knowledge_key_owner"),
    )
    op.create_index("ix_project_knowledge_key", "project_knowledge", ["key"])
    op.create_index("ix_project_knowledge_project_key", "project_knowledge", ["project_key"])
    op.create_index("ix_project_knowledge_status", "project_knowledge", ["status"])
    op.create_index("ix_project_knowledge_owner_id", "project_knowledge", ["owner_id"])


def downgrade() -> None:
    op.drop_table("project_knowledge")
    op.drop_table("project_config")
    op.drop_table("projects")
