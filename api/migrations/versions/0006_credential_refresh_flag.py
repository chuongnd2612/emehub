"""Track whether a stored Claude credential carries a refresh token (issue #63).

A Claude OAuth *access* token lives hours, so a real ``.credentials.json`` is
past its ``expiresAt`` almost immediately — but the file also carries a
**refresh token**, and the CLI mints a new access token from it transparently.
Nothing in the hub knew that token existed, so every uploaded credential turned
red within an afternoon.

The column is a **boolean, not the token**. The refresh token itself stays
inside the ``enc::v1:`` envelope in ``credentials`` and is never copied out —
that invariant is the whole reason this is one bit rather than a second secret
column.

Nullable with no default, deliberately: NULL means "not looked at yet". Reading
the flag for an existing row would mean decrypting every blob inside a
migration, which needs ``EMEHUB_ENCRYPTION_KEY`` to be correct at upgrade time
and fails the whole deploy if it is not. Instead
``services.claude_credentials.backfill_refresh_flag`` resolves NULL on the next
read of each row, once, so existing rows self-heal.

Revision ID: 0006_credential_refresh_flag
Revises: 0005_provider_connections
Create Date: 2026-07-29
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# Kept to 28 characters: `alembic_version.version_num` is varchar(32) on
# Postgres, and an over-long id fails the stamp *after* the DDL has run.
revision: str = "0006_credential_refresh_flag"
down_revision: str | None = "0005_provider_connections"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "claude_credentials",
        sa.Column("has_refresh_token", sa.Boolean(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("claude_credentials", "has_refresh_token")
