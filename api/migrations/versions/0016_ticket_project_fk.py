"""``tickets.project_id`` becomes a real FK, with a backfill and a loud residue (#217).

Slice 1 of the project-containment epic (#223, ``docs/PROJECT-CONTAINMENT-HANDOFF.md`` §4).

## Two problems, and the second is the dangerous one

**Referential integrity.** ``0002_tickets`` created ``project_id`` as a bare
indexed ``Integer``. Nothing constrained it to an existing project, so a stale
or fabricated id was indistinguishable from a real one. It becomes
``REFERENCES projects(id) ON DELETE SET NULL`` here.

**Tickets that belong to no project.** Rows synced before project stamping have
``project_id IS NULL``. Once the ticket list is project-scoped they appear
nowhere — a silent disappearance of data, not a display bug. So this migration
does three things in order, and the third is not optional.

1. **Detach the dangling.** ``project_id`` values that point at no project are
   set to NULL. They have to be: the constraint cannot be created while they
   exist, and *what* they pointed at is unrecoverable. The count is logged.
2. **Backfill from ``connection_id``.** A project's ticket source is
   ``project_config.work_item_connection_id`` and a project's configuration is
   joined to the registry by ``key`` *within one ownership namespace*
   (``projects.key`` ↔ ``project_config.key``, both scoped by ``owner_id`` —
   ``services/project_service.own_then_shared``). So a ticket's connection
   resolves to a project through that pair. Resolution follows the hub's own →
   shared precedence: the ticket owner's own binding wins, the shared namespace
   is the fallback, and **an ambiguous connection resolves to nothing** — two
   projects binding one connection is not a tie this migration is entitled to
   break, and guessing would attribute work items to the wrong project.
3. **Log the residue.** Whatever is still NULL is reported at INFO, on the
   ``alembic.runtime.migration`` channel, so the number sits next to the
   "Running upgrade" line in ordinary container output. A migration that runs
   quietly and leaves tickets invisible is the worst outcome available here.
   Those rows are reachable: ``GET /tickets?unassigned=true`` and the
   ``unassigned`` field of ``GET /projects/ticket-counts``.

## Why ``ON DELETE SET NULL``

CASCADE would destroy mirrored work items as a side effect of deleting a project
row, and a re-sync needs the connection that was bound to the project being
deleted, so the loss is not undoable from the hub. RESTRICT reads better — and
the service layer *does* already refuse (``project_service.ProjectHasTickets``,
which reports the count) — but ``projects.owner_id`` is ``ON DELETE CASCADE``
from ``users``, so a database-level RESTRICT would abort an unrelated member
delete with an ``IntegrityError``. SET NULL leaves the service-layer refusal as
the ordinary path and makes the cascade path land its rows in the Unassigned
bucket, which this slice makes visible and countable.

## Portability

The suite runs on SQLite; production is Postgres 16. SQLite cannot ALTER a table
to add a constraint, so both the create and the drop go through
``op.batch_alter_table`` — a plain ``ALTER TABLE`` on Postgres, a table rewrite
on SQLite. Nothing here is dialect-specific SQL.

Revision ID: 0016_ticket_project_fk
Revises: 0015_repair_effort_column
Create Date: 2026-08-27
"""

from __future__ import annotations

import logging

import sqlalchemy as sa
from alembic import op

revision = "0016_ticket_project_fk"
down_revision = "0015_repair_effort_column"
branch_labels = None
depends_on = None

#: Alembic's own channel, so the counts appear beside "Running upgrade …" in
#: normal migration output rather than in a logger nobody has configured.
log = logging.getLogger("alembic.runtime.migration")

FK_NAME = "fk_tickets_project_id_projects"


def _detach_dangling(conn) -> int:  # noqa: ANN001
    """NULL every ``project_id`` that points at no project. Returns the count.

    Counted first and updated second: ``rowcount`` is not reliable across every
    driver, and the number is going into a log line that has to be true.
    """
    count = conn.execute(
        sa.text(
            "SELECT COUNT(*) FROM tickets WHERE project_id IS NOT NULL "
            "AND project_id NOT IN (SELECT id FROM projects)"
        )
    ).scalar_one()
    if count:
        conn.execute(
            sa.text(
                "UPDATE tickets SET project_id = NULL WHERE project_id IS NOT NULL "
                "AND project_id NOT IN (SELECT id FROM projects)"
            )
        )
    return int(count or 0)


def _bindings(conn) -> dict[tuple[int, int | None], int | None]:  # noqa: ANN001
    """``(work_item_connection_id, owner_id) -> project id``, ``None`` if ambiguous.

    The join is the real one, not a guess: ``project_config`` names its ticket
    source in ``work_item_connection_id`` and is tied to the registry row by
    ``key`` inside a single ownership namespace.
    """
    rows = conn.execute(
        sa.text(
            "SELECT pc.work_item_connection_id AS connection_id, "
            "       pc.owner_id                AS owner_id, "
            "       p.id                       AS project_id "
            "  FROM project_config pc "
            "  JOIN projects p ON p.key = pc.key "
            "   AND ((p.owner_id IS NULL AND pc.owner_id IS NULL) "
            "        OR p.owner_id = pc.owner_id) "
            " WHERE pc.work_item_connection_id IS NOT NULL"
        )
    ).mappings()

    found: dict[tuple[int, int | None], set[int]] = {}
    for row in rows:
        key = (int(row["connection_id"]), row["owner_id"])
        found.setdefault(key, set()).add(int(row["project_id"]))
    # A connection bound by two projects in the same namespace is left
    # unresolved on purpose — see the module docstring.
    return {
        key: (next(iter(ids)) if len(ids) == 1 else None)
        for key, ids in found.items()
    }


def _backfill(conn) -> int:  # noqa: ANN001
    """Stamp ``project_id`` from ``connection_id``. Returns rows resolved."""
    bindings = _bindings(conn)
    if not bindings:
        return 0

    candidates = conn.execute(
        sa.text(
            "SELECT id, connection_id, owner_id FROM tickets "
            " WHERE project_id IS NULL AND connection_id IS NOT NULL"
        )
    ).mappings()

    # Grouped by target project so the writes are one statement per project,
    # not one per ticket.
    groups: dict[int, list[int]] = {}
    for row in candidates:
        connection_id = int(row["connection_id"])
        owner_id = row["owner_id"]
        # own → shared → nothing, the hub's resolution rule everywhere else.
        project_id = bindings.get((connection_id, owner_id))
        if project_id is None and owner_id is not None:
            project_id = bindings.get((connection_id, None))
        if project_id is None:
            continue
        groups.setdefault(project_id, []).append(int(row["id"]))

    resolved = 0
    for project_id, ticket_ids in groups.items():
        statement = sa.text(
            "UPDATE tickets SET project_id = :project_id WHERE id IN :ticket_ids"
        ).bindparams(sa.bindparam("ticket_ids", expanding=True))
        conn.execute(statement, {"project_id": project_id, "ticket_ids": ticket_ids})
        resolved += len(ticket_ids)
    return resolved


def upgrade() -> None:
    conn = op.get_bind()

    detached = _detach_dangling(conn)
    resolved = _backfill(conn)
    unassigned = int(
        conn.execute(
            sa.text("SELECT COUNT(*) FROM tickets WHERE project_id IS NULL")
        ).scalar_one()
        or 0
    )

    log.info(
        "tickets.project_id: %d row(s) detached from a project that no longer "
        "exists, %d row(s) backfilled from connection_id",
        detached,
        resolved,
    )
    if unassigned:
        log.info(
            "tickets.project_id: %d row(s) could NOT be attributed to a project "
            "and are now the Unassigned bucket — GET /tickets?unassigned=true, "
            "and the `unassigned` field of GET /projects/ticket-counts",
            unassigned,
        )
    else:
        log.info("tickets.project_id: every ticket belongs to a project")

    with op.batch_alter_table("tickets") as batch:
        batch.create_foreign_key(
            FK_NAME, "projects", ["project_id"], ["id"], ondelete="SET NULL"
        )


def downgrade() -> None:
    """Drop the constraint. The backfilled values stay.

    Nothing is un-backfilled: a stamped ``project_id`` is *correct* data that
    happens to have been derived here, and reverting the schema is not a reason
    to make tickets invisible again. Same for the detached dangling rows — what
    they pointed at was already gone.
    """
    with op.batch_alter_table("tickets") as batch:
        batch.drop_constraint(FK_NAME, type_="foreignkey")
