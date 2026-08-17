"""Keep the work item's provider URL instead of discarding it.

All three adapters normalise a ``url`` — Azure DevOps builds
``{org}/{project}/_workitems/edit/{id}``, Jira builds ``{base}/browse/{key}``,
GitHub passes ``html_url`` through — and the hub dropped every one of them for
want of a column. An agent reading ``GET /tickets/{external_id}`` therefore had
no way to send a human back to the source, which is the one action a read-only
mirror should always be able to offer.

Additive, defaulted and never null: existing rows get ``''`` and are filled by
the next sync, so nothing has to be backfilled from the provider here. A blank
URL and a missing URL are the same thing to a consumer — both mean "no link to
offer" — so there is no reason for this column to be nullable.

Revision ID: 0011_ticket_url
Revises: 0010_project_guid
Create Date: 2026-08-17
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0011_ticket_url"
down_revision = "0010_project_guid"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # `server_default=""` fills the existing rows in one statement; it is then
    # dropped so the application default is the only one, matching every other
    # text column on this table.
    op.add_column(
        "tickets",
        sa.Column("url", sa.String(length=1000), nullable=False, server_default=""),
    )
    with op.batch_alter_table("tickets") as batch:
        batch.alter_column("url", existing_type=sa.String(length=1000), server_default=None)


def downgrade() -> None:
    op.drop_column("tickets", "url")
