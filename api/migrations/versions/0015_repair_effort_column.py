"""Add ``user_model_preferences.effort`` where an earlier ``0013`` left it out (#208).

``0013_model_preferences`` was edited in place after it had already run against
the suite's Postgres: the ``effort`` column was added to the file once the
thinking-level chips became a real ``--effort`` value. Alembic never re-runs an
applied revision, so on those databases the column was simply never created,
while the file claims it exists. ``GET /me/model-preferences`` then fails with
``UndefinedColumn`` and the Models tab renders nothing but an error.

Editing ``0013`` a third time would not help — the revision is stamped and will
not run again. The repair has to be a new revision.

This one is deliberately conditional. A database created after ``0013`` was
fixed already has the column, and adding it unconditionally would fail there;
one created before does not. Inspecting the live schema is the only thing that
tells the two apart, so that is what it does.

``downgrade`` is a no-op on purpose. The column is part of ``0013``'s declared
shape, so dropping it here would leave a database that ``0013`` claims to have
built incorrectly. ``0013``'s own downgrade drops the whole table.

Revision ID: 0015_repair_effort_column
Revises: 0014_drop_fast_model
Create Date: 2026-08-25
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0015_repair_effort_column"
down_revision = "0014_drop_fast_model"
branch_labels = None
depends_on = None

_TABLE = "user_model_preferences"
_COLUMN = "effort"


def _has_effort() -> bool:
    inspector = sa.inspect(op.get_bind())
    if _TABLE not in inspector.get_table_names():
        return True
    return any(col["name"] == _COLUMN for col in inspector.get_columns(_TABLE))


def upgrade() -> None:
    if _has_effort():
        return
    op.add_column(
        _TABLE,
        sa.Column(_COLUMN, sa.String(length=16), nullable=False, server_default=""),
    )


def downgrade() -> None:
    """Intentionally empty — see the module docstring."""
