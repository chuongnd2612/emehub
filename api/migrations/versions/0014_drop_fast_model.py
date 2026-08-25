"""Drop ``user_model_preferences.fast_model`` (#197).

The table shipped one migration ago (#190, ``0013``) on the argument that a
stored setting has to decide something. Two of its three columns do:
``main_model`` and ``effort`` are resolved before every Claude CLI invocation
and passed as ``--model`` and ``--effort``. ``fast_model`` never was. It was
written, validated, returned on the wire and rendered as a second dropdown, and
no code path read it.

Nor could one, as the hub is built: it makes exactly one kind of Claude call —
a knowledge build (ADR 0007) — so there is no cheaper, secondary invocation for
a fast model to be spent on. Wiring it would have meant inventing the second
call, which is agent work, not the hub's.

So the column goes rather than staying as a preference that persists and
decides nothing. Nothing reads it, so nothing is lost: dropping it changes no
build's behaviour, and the rows keep whatever ``main_model`` and ``effort``
their owners chose.

``downgrade`` restores the column empty, with the same ``server_default=""``
``0013`` created it with — empty being "no choice made", the whole table's
convention — because the values it held decided nothing and are not worth
carrying a data-preserving path for.

Revision ID: 0014_drop_fast_model
Revises: 0013_model_preferences
Create Date: 2026-08-25
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0014_drop_fast_model"
down_revision = "0013_model_preferences"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_column("user_model_preferences", "fast_model")


def downgrade() -> None:
    op.add_column(
        "user_model_preferences",
        sa.Column("fast_model", sa.String(length=64), nullable=False, server_default=""),
    )
