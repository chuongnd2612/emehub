"""Persisted knowledge-build progress (issue #68).

A build is minutes long and, until now, wrote the row exactly twice: the flip to
``indexing`` and the terminal ``indexed``/``error``. Everything in between was
invisible, so the UI could only show a spinner and hope.

Five columns make the stages real and readable by any worker:

``build_stage`` / ``build_step``
    Where the build is, as a key and as its 1-based ordinal. Denormalising the
    ordinal keeps "3 of 5" out of the client's knowledge of the stage vocabulary.

``build_message``
    The live human-readable line. During the Claude stage it is derived from the
    CLI's own event stream, scrubbed and truncated before it reaches this column.

``build_started_at`` / ``build_heartbeat_at``
    The elapsed clock, and the orphan test. A container that dies mid-build
    leaves a row at ``indexing`` with no worker behind it; the heartbeat stops
    being refreshed, and after ``EMEHUB_KNOWLEDGE_BUILD_STALE_S`` the API can say
    so honestly instead of spinning forever.

Every column is nullable or defaulted, so existing rows need no backfill: a row
that has never been built reads as ``("", 0, "", NULL, NULL)``, which is exactly
"no progress recorded".

Revision ID: 0007_knowledge_progress
Revises: 0006_credential_refresh_flag
Create Date: 2026-07-30
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op
from app.db import UTCDateTime

# 22 characters. `alembic_version.version_num` is varchar(32) on Postgres and an
# over-long id fails the stamp *after* the DDL has run (see 0006, and the guard
# in tests/test_app_wiring.py).
revision: str = "0007_knowledge_progress"
down_revision: str | None = "0006_credential_refresh_flag"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "project_knowledge",
        sa.Column("build_stage", sa.String(length=32), nullable=False, server_default=""),
    )
    op.add_column(
        "project_knowledge",
        sa.Column("build_step", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "project_knowledge",
        sa.Column("build_message", sa.String(length=400), nullable=False, server_default=""),
    )
    op.add_column(
        "project_knowledge",
        sa.Column("build_started_at", UTCDateTime(), nullable=True),
    )
    op.add_column(
        "project_knowledge",
        sa.Column("build_heartbeat_at", UTCDateTime(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("project_knowledge", "build_heartbeat_at")
    op.drop_column("project_knowledge", "build_started_at")
    op.drop_column("project_knowledge", "build_message")
    op.drop_column("project_knowledge", "build_step")
    op.drop_column("project_knowledge", "build_stage")
