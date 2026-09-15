"""``project_knowledge`` gains sync columns (#279).

A lightweight ``POST /projects/{key}/repos/{repo}/pull`` (issue #279) refreshes a
repository's checkout — fetch/reset against its configured branch — with no
Claude build attached. That needs somewhere to record what it did that is
distinct from the build columns already on the row: ``last_indexed``/``version``
only ever move on a build, and a sync must not pretend to be one.

``last_synced_at`` and ``synced_commit_sha`` are both nullable: every existing
row predates syncing and has neither, and that is exactly what "never synced"
should look like — not a sentinel value.

Revision ID: 0018_knowledge_sync_columns
Revises: 0017_saved_query_project
Create Date: 2026-09-15
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0018_knowledge_sync_columns"
down_revision: str | None = "0017_saved_query_project"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("project_knowledge") as batch:
        batch.add_column(sa.Column("last_synced_at", sa.DateTime(), nullable=True))
        batch.add_column(sa.Column("synced_commit_sha", sa.String(length=64), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("project_knowledge") as batch:
        batch.drop_column("synced_commit_sha")
        batch.drop_column("last_synced_at")
