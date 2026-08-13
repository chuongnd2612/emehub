"""A stable external identity for projects.

Consumers outside the hub need a handle that is neither ``key`` (derived from the
name, and regenerable) nor ``id`` (an internal surrogate, and enumerable). Q-Agent
already identifies projects by GUID on its side; this is the hub agreeing on the
same shape so the two systems can talk about a project without either one's naming
or numbering leaking into the other.

``key`` and ``id`` are untouched and keep working. There is no cutover here — the
GUID is added alongside, permanently, because a hard swap across every call site is
how this class of change breaks quietly.

The column is added nullable, backfilled row by row, and only then made NOT NULL.
A server-side default cannot be used for the backfill: every existing row would get
one shared value and the unique index would reject the lot. Each row needs its own.

Revision ID: 0010_project_guid
Revises: 0009_saved_queries
Create Date: 2026-08-13
"""

from __future__ import annotations

import uuid

import sqlalchemy as sa
from alembic import op

revision = "0010_project_guid"
down_revision = "0009_saved_queries"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("projects", sa.Column("guid", sa.String(length=36), nullable=True))

    # Backfill per row. `UPDATE ... SET guid = <one uuid>` would assign the SAME
    # value to every project and then fail the unique index — or, worse on a
    # backend without one, succeed and leave every project sharing an identity.
    connection = op.get_bind()
    rows = connection.execute(sa.text("SELECT id FROM projects WHERE guid IS NULL")).fetchall()
    for (project_id,) in rows:
        connection.execute(
            sa.text("UPDATE projects SET guid = :guid WHERE id = :id"),
            {"guid": str(uuid.uuid4()), "id": project_id},
        )

    # `batch_alter_table`, not a bare `alter_column`: SQLite has no
    # `ALTER COLUMN ... SET NOT NULL` and errors on the generated DDL. Batch mode
    # emits the copy-and-rename SQLite needs and a plain ALTER everywhere else, so
    # one migration serves the test backend and Postgres alike.
    with op.batch_alter_table("projects") as batch:
        batch.alter_column("guid", existing_type=sa.String(length=36), nullable=False)

    op.create_index("ix_projects_guid", "projects", ["guid"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_projects_guid", table_name="projects")
    op.drop_column("projects", "guid")
