"""Let an admin turn an agent off without a deploy (#186).

Every other agent knob is environment configuration read once at boot. Whether a
product is open to users is a decision an admin makes and unmakes, so it is a row:
flipping it takes effect on the next request rather than the next deploy.

Deliberately **not** seeded. There is no row until somebody turns an agent off,
and a missing row reads as enabled — a table that had to be populated before the
suite worked would be a new way for a fresh install to come up broken, and the
safe default for "is this product open?" is the state the suite has always been
in.

``updated_by`` is ``SET NULL`` rather than cascading: the record of *what* the
setting is must outlive the account that set it.

Revision ID: 0012_agent_availability
Revises: 0011_ticket_url
Create Date: 2026-08-25
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0012_agent_availability"
down_revision = "0011_ticket_url"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "agent_availability",
        sa.Column("key", sa.String(length=32), primary_key=True),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column(
            "updated_by",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_table("agent_availability")
