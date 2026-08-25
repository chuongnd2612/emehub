"""Per-user Claude model preferences (#190).

The Models tab of Claude Settings held its choices in React state, so they were
lost on reload and read by nothing. This is the table behind them, and the hub's
own knowledge builds read it: a build resolves its model and its Claude CLI
``--effort`` level from the row owner's preferences before it invokes the CLI.

Every column defaults to the empty string rather than to a model id, because
empty means "no choice made, use the system default" — the same shape as
``agent_availability``, where an absent row means enabled. Seeding real values
would mean this migration decided what everybody's builds run on.

Deliberately **not** seeded, and deliberately keyed on the user rather than
carrying a surrogate id: one row per person at most, created by their first save.
A user with no row gets the defaults from ``app.config``, so an empty table is
the normal state of a fresh install rather than a broken one.

``ondelete="CASCADE"``, unlike the audit and usage tables: a preference has no
meaning without the account that holds it, and there is nothing here worth
outliving it.

Revision ID: 0013_model_preferences
Revises: 0012_agent_availability
Create Date: 2026-08-25
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0013_model_preferences"
down_revision = "0012_agent_availability"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "user_model_preferences",
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("main_model", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("fast_model", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("effort", sa.String(length=16), nullable=False, server_default=""),
        sa.Column(
            "updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()
        ),
    )


def downgrade() -> None:
    op.drop_table("user_model_preferences")
