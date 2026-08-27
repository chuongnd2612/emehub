"""``saved_ticket_queries`` gain a project axis (#222).

Slice 6 of the project-containment epic (#223), and the schema half of the
reversal recorded in
[ADR 0011](../../../docs/adr/0011-project-containment-in-the-hub.md) — the model's
own docstring argued *against* project scoping, and is rewritten in the same
commit.

## What changes, and what deliberately does not

``project_id`` is added **nullable**, and **no row is rewritten.** Every query
that exists today — a member's own and every shipped preset — stays
``project_id IS NULL``, which is read as *workspace-wide*: offered in any project
whose ``destination`` matches. Reinterpreting existing rows as belonging to
whichever project looked closest would attribute a person's saved filter to a
container they never chose. Queries saved from inside a project bind to it from
here on.

Built-ins are not touched at all. They stay in the shared namespace with no
project, and stay usable, copyable, and refused (409) on edit or delete.

## Why ``ON DELETE CASCADE``

The other direction was tempting: SET NULL, and the query survives its project as
workspace-wide. That is precisely the failure ADR 0011 exists to prevent. A query
bound to a project names *that* project's area paths, iterations and states; left
behind with no project it would be silently *widened* — offered in every project
on the matching destination, where its clauses mean something else or nothing at
all, while its ``description`` still describes the narrower query. A saved query
is one of the artefacts the hub owns *about* a project, like
``project_config`` and ``project_knowledge``, both of which
``project_service.delete_project`` already removes with the project. CASCADE says
the same thing at the schema level.

#217 chose SET NULL for ``tickets.project_id`` and the difference is not an
inconsistency: a ticket is a mirror of a real work item that exists whether or not
the hub has a project for it, and destroying it is not undoable from the hub. A
saved query is hub-native and re-creatable in one action.

The RESTRICT hazard #217 documented does not apply. ``projects.owner_id`` is
``ON DELETE CASCADE`` from ``users``, so a member delete deletes their projects; a
RESTRICT here would abort that with an ``IntegrityError``, while CASCADE simply
follows. A *shared* query bound to a member's private project goes with that
project — correct, since the container it was scoped to is gone.

## Why the unique constraint gains the column

``uq_saved_query_name`` becomes ``(owner_id, project_id, destination, name)``.
Without ``project_id`` in it, "Backlog triage" in one project would block
"Backlog triage" in the next, which is the whole point of the scope.

Both engines treat NULLs as **distinct** in a unique index — Postgres by default
(``NULLS NOT DISTINCT`` is deliberately *not* used, so SQLite and Postgres agree),
SQLite always. So this constraint, like the three-column one it replaces, only
bites when every column is non-NULL: it caught nothing in the shared namespace
before and it catches nothing with ``project_id IS NULL`` now. That is why the
real enforcement is, and remains, ``services/saved_queries.create_query``, whose
clash check compares NULLs with ``IS NULL`` and therefore covers the shared and
workspace-wide cases the index cannot. The constraint is the backstop, and it is
widened here only so that it stops refusing something legitimate.

Revision ID: 0017_saved_query_project
Revises: 0016_ticket_project_fk
Create Date: 2026-08-27
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0017_saved_query_project"
down_revision: str | None = "0016_ticket_project_fk"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

UQ_NAME = "uq_saved_query_name"
FK_NAME = "fk_saved_ticket_queries_project_id_projects"
IX_NAME = "ix_saved_ticket_queries_project_id"


def upgrade() -> None:
    # The suite runs on SQLite and production on Postgres 16. SQLite cannot ALTER
    # a table to add or drop a constraint, so both go through batch mode: a plain
    # ALTER TABLE on Postgres, a table rewrite on SQLite. No dialect-specific SQL.
    with op.batch_alter_table("saved_ticket_queries") as batch:
        batch.add_column(sa.Column("project_id", sa.Integer(), nullable=True))
        batch.create_foreign_key(
            FK_NAME, "projects", ["project_id"], ["id"], ondelete="CASCADE"
        )
        batch.drop_constraint(UQ_NAME, type_="unique")
        batch.create_unique_constraint(
            UQ_NAME, ["owner_id", "project_id", "destination", "name"]
        )
    op.create_index(IX_NAME, "saved_ticket_queries", ["project_id"])


def downgrade() -> None:
    """Drop the column, restoring ``(owner_id, destination, name)``.

    Going back can collide: two queries that differ only by project are legal
    forward and are one duplicate name backward. Workspace-wide rows and built-ins
    keep their names unconditionally — they are the shape that existed before this
    revision — and among project-bound rows the lowest id keeps it. The rest are
    suffixed with their project id rather than deleted: a renamed saved query is
    recoverable, a deleted one is not.
    """
    conn = op.get_bind()
    rows = conn.execute(
        sa.text(
            "SELECT id, owner_id, destination, name, project_id "
            "  FROM saved_ticket_queries ORDER BY id"
        )
    ).mappings()

    # Every workspace-wide key is claimed first, whatever its id, so no row that
    # predates this revision is ever the one renamed.
    project_rows = []
    seen: set[tuple[object, object, object]] = set()
    for row in rows:
        key = (row["owner_id"], row["destination"], row["name"])
        if row["project_id"] is None:
            seen.add(key)
        else:
            project_rows.append((row["id"], key, row["project_id"], row["name"]))

    for row_id, key, project_id, name in project_rows:
        if key in seen:
            renamed = f"{name} (project {project_id})"[:120]
            conn.execute(
                sa.text("UPDATE saved_ticket_queries SET name = :name WHERE id = :id"),
                {"name": renamed, "id": row_id},
            )
        else:
            seen.add(key)

    op.drop_index(IX_NAME, table_name="saved_ticket_queries")
    with op.batch_alter_table("saved_ticket_queries") as batch:
        batch.drop_constraint(UQ_NAME, type_="unique")
        batch.create_unique_constraint(UQ_NAME, ["owner_id", "destination", "name"])
        batch.drop_constraint(FK_NAME, type_="foreignkey")
        batch.drop_column("project_id")
