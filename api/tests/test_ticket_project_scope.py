"""``tickets.project_id`` as a real FK, the backfill, and the Unassigned bucket (#217).

Slice 1 of the project-containment epic (#223). Four properties are asserted
here, and each one exists because its absence loses data rather than merely
looking wrong:

* **The constraint holds.** A ``project_id`` that names no project is refused by
  the database, not silently stored.
* **``ON DELETE SET NULL`` behaves.** A deleted project leaves its mirrored work
  items in the Unassigned bucket. It does not destroy them, and it does not
  orphan them at a row that no longer exists.
* **The backfill resolves through ``connection_id``**, using the real binding
  (``project_config.work_item_connection_id`` joined to ``projects`` by ``key``
  within one ownership namespace) — and leaves an ambiguous or unbindable
  connection alone rather than guessing.
* **Nothing disappears.** The number of rows with ``project_id IS NULL`` equals
  the number the API reports for the bucket, and the bucket is listable.

Two projects are seeded on **different providers** (one Azure DevOps, one Jira),
following ``../q-agent/api/scripts/probe_setup_732.py``: with a single project
"the other project's rows must not appear" is a vacuous assertion, and scoping
that happens to work cannot be told from scoping that works.
"""

from __future__ import annotations

import pytest
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError

PASSWORD = "password12345"
PREVIOUS_REVISION = "0015_repair_effort_column"


# ---------------------------------------------------------------- helpers
def _alembic(direction: str, revision: str) -> None:
    """Drive the *real* migrations, the same way ``app.db.run_migrations`` does."""
    from alembic import command
    from alembic.config import Config

    from app.config import API_DIR, settings

    cfg = Config(str(API_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(API_DIR / "migrations"))
    cfg.set_main_option("sqlalchemy.url", settings.database_url)
    getattr(command, direction)(cfg, revision)


def _project(db, key: str, owner_id: int | None, name: str = ""):
    from app.models.project import Project

    row = Project(key=key, name=name or key, owner_id=owner_id)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _connection(db, kind: str, owner_id: int | None):
    from app.models.provider_connection import ProviderConnection, default_capabilities

    row = ProviderConnection(
        kind=kind,
        label=f"{kind} account",
        config={},
        capabilities=default_capabilities(kind),
    )
    row.owner_id = owner_id
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _config(db, key: str, owner_id: int | None, work_item_connection_id: int | None):
    from app.models.project_config import ProjectConfig

    row = ProjectConfig(
        key=key,
        name=key,
        work_item_connection_id=work_item_connection_id,
        repos=[],
        environments=[],
        test_accounts=[],
        extra={},
        owner_id=owner_id,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _ticket(db, external_id: str, *, owner_id, **fields):
    from app.models.ticket import Ticket

    row = Ticket(
        external_id=external_id,
        provider_kind=fields.pop("provider_kind", "ado"),
        title=f"Work item {external_id}",
        labels=[],
        acceptance_criteria=[],
        comments=[],
        attachments=[],
        linked_prs=[],
        owner_id=owner_id,
        **fields,
    )
    db.add(row)
    db.commit()
    return row


@pytest.fixture
def two_projects(db_session, make_user, client, auth_headers):
    """The negative control: two projects, two providers, tickets in each, plus
    rows that belong to no project at all.

    Returns everything the assertions need, including the auth header for the
    one member who owns all of it.
    """
    user = make_user("scope@emesoft.net", PASSWORD)
    ado = _connection(db_session, "azure_devops", user.id)
    jira = _connection(db_session, "jira", user.id)

    platform = _project(db_session, "surency-platform", user.id, "Surency Platform")
    claims = _project(db_session, "claims-portal", user.id, "Claims Portal")
    _config(db_session, "surency-platform", user.id, ado.id)
    _config(db_session, "claims-portal", user.id, jira.id)

    _ticket(
        db_session, "SUR-1", owner_id=user.id, project_id=platform.id,
        connection_id=ado.id, provider_kind="ado",
    )
    _ticket(
        db_session, "SUR-2", owner_id=user.id, project_id=platform.id,
        connection_id=ado.id, provider_kind="ado",
    )
    _ticket(
        db_session, "CLM-9001", owner_id=user.id, project_id=claims.id,
        connection_id=jira.id, provider_kind="jira",
    )
    # Belongs to no project and to no connection — the residue the bucket exists
    # for. Nothing can attribute this row, and it must still be reachable.
    _ticket(db_session, "ORPHAN-1", owner_id=user.id)

    return {
        "user": user,
        "headers": auth_headers("scope@emesoft.net", PASSWORD),
        "platform": platform,
        "claims": claims,
        "ado": ado,
        "jira": jira,
    }


# ---------------------------------------------------------------- the constraint
def test_the_column_is_a_foreign_key_that_nulls_on_delete(workspace_dir):
    """Schema-level, so a future migration cannot quietly drop either half."""
    import app.db as db_module

    inspector = inspect(db_module.engine)
    fks = [
        fk
        for fk in inspector.get_foreign_keys("tickets")
        if fk["constrained_columns"] == ["project_id"]
    ]
    assert len(fks) == 1, inspector.get_foreign_keys("tickets")
    assert fks[0]["referred_table"] == "projects"
    assert fks[0]["referred_columns"] == ["id"]
    assert (fks[0].get("options") or {}).get("ondelete", "").upper() == "SET NULL"


def test_a_project_id_that_does_not_exist_is_refused(db_session, make_user):
    """The whole point of the FK: a fabricated id used to be indistinguishable
    from a real one."""
    user = make_user("fk@emesoft.net", PASSWORD)
    with pytest.raises(IntegrityError):
        _ticket(db_session, "GHOST-1", owner_id=user.id, project_id=987654)
    db_session.rollback()


def test_deleting_a_project_moves_its_tickets_to_the_bucket_not_the_bin(
    db_session, make_user
):
    """``ON DELETE SET NULL``, exercised rather than asserted from the schema.

    The ordinary delete path is still *refused* by
    ``project_service.delete_project``; this is the cascade path, and what it
    must not do is destroy a mirror of real work items.
    """
    from app.models.ticket import Ticket

    user = make_user("cascade@emesoft.net", PASSWORD)
    project = _project(db_session, "doomed", user.id)
    _ticket(db_session, "SUR-77", owner_id=user.id, project_id=project.id)

    db_session.execute(text("DELETE FROM projects WHERE id = :id"), {"id": project.id})
    db_session.commit()
    db_session.expire_all()

    row = db_session.query(Ticket).filter_by(external_id="SUR-77").one()
    assert row.project_id is None  # in the bucket, still here


# ---------------------------------------------------------------- the migration
def test_the_migration_backfills_from_connection_id_and_leaves_a_visible_residue(
    workspace_dir,
):
    """Downgrade to ``0015``, plant the exact rows the hub has in the wild, and
    run ``0016`` forward for real.

    Four kinds of row are planted, because the migration has to treat them
    differently: one resolvable through its connection, one whose connection is
    bound by *two* projects (ambiguous — must stay NULL), one whose
    ``project_id`` points at a project that no longer exists (must be detached),
    and one with nothing to go on at all.
    """
    import app.db as db_module
    from app.models.ticket import Ticket
    from app.models.user import User
    from app.services import auth_service

    _alembic("downgrade", PREVIOUS_REVISION)

    setup = db_module.SessionLocal()
    try:
        user = User(
            email="backfill@emesoft.net",
            first_name="Back",
            last_name="Fill",
            role="member",
            password_hash=auth_service.hash_password(PASSWORD),
            is_active=True,
        )
        setup.add(user)
        setup.commit()
        setup.refresh(user)

        ado = _connection(setup, "azure_devops", user.id)
        jira = _connection(setup, "jira", user.id)
        shared = _connection(setup, "github", None)

        platform = _project(setup, "surency-platform", user.id)
        claims = _project(setup, "claims-portal", user.id)
        # Two projects binding ONE connection: an ambiguity the migration is not
        # entitled to break.
        _project(setup, "twin-a", user.id)
        _project(setup, "twin-b", user.id)
        # A shared-namespace project, to prove own → shared fallback resolves.
        shared_project = _project(setup, "shared-app", None)

        _config(setup, "surency-platform", user.id, ado.id)
        _config(setup, "claims-portal", user.id, jira.id)
        _config(setup, "twin-a", user.id, 4242)
        _config(setup, "twin-b", user.id, 4242)
        _config(setup, "shared-app", None, shared.id)

        # Resolvable: connection_id -> project_config -> project.
        _ticket(setup, "SUR-1", owner_id=user.id, connection_id=ado.id)
        _ticket(
            setup, "CLM-1", owner_id=user.id, connection_id=jira.id, provider_kind="jira"
        )
        # Resolvable only through the shared namespace.
        _ticket(setup, "SHARED-1", owner_id=user.id, connection_id=shared.id)
        # Ambiguous — two projects claim connection 4242.
        _ticket(setup, "TWIN-1", owner_id=user.id, connection_id=4242)
        # A connection nothing is bound to.
        _ticket(setup, "NOBODY-1", owner_id=user.id, connection_id=9999)
        # Dangling: project 123456 does not exist. Only insertable because the
        # constraint is not there yet, which is exactly the state 0016 inherits.
        _ticket(setup, "DANGLE-1", owner_id=user.id, project_id=123456)
        # Nothing to go on.
        _ticket(setup, "ORPHAN-1", owner_id=user.id)

        expected = {
            "SUR-1": platform.id,
            "CLM-1": claims.id,
            "SHARED-1": shared_project.id,
        }
        setup.commit()
    finally:
        setup.close()

    _alembic("upgrade", "head")

    check = db_module.SessionLocal()
    try:
        rows = {t.external_id: t.project_id for t in check.query(Ticket).all()}
    finally:
        check.close()

    for external_id, project_id in expected.items():
        assert rows[external_id] == project_id, external_id
    # The residue: never guessed at, never hidden.
    for external_id in ("TWIN-1", "NOBODY-1", "DANGLE-1", "ORPHAN-1"):
        assert rows[external_id] is None, external_id


def test_the_migration_reverses_with_null_rows_present(workspace_dir):
    """Down and up again on a database that has an Unassigned bucket in it.

    The constraint goes; the rows stay. Un-backfilling would put tickets back
    where nothing can see them, which is the failure this slice exists to fix.
    """
    import app.db as db_module
    from app.models.ticket import Ticket
    from app.models.user import User
    from app.services import auth_service

    setup = db_module.SessionLocal()
    try:
        user = User(
            email="reverse@emesoft.net",
            first_name="Re",
            last_name="Verse",
            role="member",
            password_hash=auth_service.hash_password(PASSWORD),
            is_active=True,
        )
        setup.add(user)
        setup.commit()
        setup.refresh(user)
        project = _project(setup, "shop", user.id)
        _ticket(setup, "SUR-1", owner_id=user.id, project_id=project.id)
        _ticket(setup, "ORPHAN-1", owner_id=user.id)  # project_id IS NULL
        setup.commit()
        project_id = project.id
    finally:
        setup.close()

    _alembic("downgrade", PREVIOUS_REVISION)

    after_down = db_module.SessionLocal()
    try:
        assert after_down.query(Ticket).count() == 2
        rows = {t.external_id: t.project_id for t in after_down.query(Ticket).all()}
        assert rows == {"SUR-1": project_id, "ORPHAN-1": None}
        inspector = inspect(db_module.engine)
        assert not [
            fk
            for fk in inspector.get_foreign_keys("tickets")
            if fk["constrained_columns"] == ["project_id"]
        ]
    finally:
        after_down.close()

    _alembic("upgrade", "head")

    after_up = db_module.SessionLocal()
    try:
        rows = {t.external_id: t.project_id for t in after_up.query(Ticket).all()}
        assert rows == {"SUR-1": project_id, "ORPHAN-1": None}
        inspector = inspect(db_module.engine)
        assert [
            fk
            for fk in inspector.get_foreign_keys("tickets")
            if fk["constrained_columns"] == ["project_id"]
        ]
    finally:
        after_up.close()


# ------------------------------------------------------- scoping, two providers
def test_a_project_scoped_list_returns_only_its_own_rows(client, two_projects):
    """One ADO project, one Jira project. Neither may leak into the other."""
    headers = two_projects["headers"]

    platform = client.get(
        f"/tickets?projectId={two_projects['platform'].id}", headers=headers
    ).json()
    assert sorted(t["externalId"] for t in platform["items"]) == ["SUR-1", "SUR-2"]
    assert platform["total"] == 2

    claims = client.get(
        f"/tickets?projectId={two_projects['claims'].id}", headers=headers
    ).json()
    assert [t["externalId"] for t in claims["items"]] == ["CLM-9001"]
    assert claims["total"] == 1
    # The provider follows the project, and the other project's provider is
    # nowhere in this answer.
    assert {t["providerKind"] for t in claims["items"]} == {"jira"}


def test_the_unassigned_selector_is_explicit_not_an_omission(client, two_projects):
    headers = two_projects["headers"]

    bucket = client.get("/tickets?unassigned=true", headers=headers).json()
    assert [t["externalId"] for t in bucket["items"]] == ["ORPHAN-1"]
    assert bucket["total"] == 1

    # Omitting projectId is a *different* question — workspace-wide — and must
    # not be read as "the ones with no project".
    everything = client.get("/tickets", headers=headers).json()
    assert everything["total"] == 4

    # Asking both at once is a contradiction, not a silent precedence rule.
    both = client.get(
        f"/tickets?projectId={two_projects['platform'].id}&unassigned=true",
        headers=headers,
    )
    assert both.status_code == 400


def test_the_bucket_count_equals_the_rows_with_no_project(
    client, db_session, two_projects
):
    """The assertion the handoff asks for: if these disagree, tickets are hidden
    somewhere."""
    from app.models.ticket import Ticket

    headers = two_projects["headers"]
    in_the_database = (
        db_session.query(Ticket)
        .filter(Ticket.project_id.is_(None), Ticket.owner_id == two_projects["user"].id)
        .count()
    )

    counts = client.get("/projects/ticket-counts", headers=headers)
    assert counts.status_code == 200, counts.text
    body = counts.json()
    assert body["unassigned"] == in_the_database == 1

    listed = client.get("/tickets?unassigned=true", headers=headers).json()
    assert listed["total"] == body["unassigned"]


def test_the_counts_endpoint_is_the_only_counting_path(client, two_projects):
    """``byProject`` must agree with both the project cards and the list, because
    all three read ``project_service.ticket_counts``."""
    headers = two_projects["headers"]
    platform = two_projects["platform"]
    claims = two_projects["claims"]

    body = client.get("/projects/ticket-counts", headers=headers).json()
    assert body["byProject"] == {str(platform.id): 2, str(claims.id): 1}
    assert body["unassigned"] == 1
    assert body["total"] == 4

    cards = {p["key"]: p["summary"]["ticketCount"] for p in client.get(
        "/projects", headers=headers
    ).json()}
    assert cards["surency-platform"] == body["byProject"][str(platform.id)]
    assert cards["claims-portal"] == body["byProject"][str(claims.id)]

    for project in (platform, claims):
        listed = client.get(f"/tickets?projectId={project.id}", headers=headers).json()
        assert listed["total"] == body["byProject"][str(project.id)]


def test_the_counts_are_scoped_to_the_caller(client, two_projects, make_user, auth_headers):
    """Another member sees none of it — not the projects, not the bucket."""
    make_user("stranger@emesoft.net", PASSWORD)
    headers = auth_headers("stranger@emesoft.net", PASSWORD)

    body = client.get("/projects/ticket-counts", headers=headers).json()
    assert body == {"byProject": {}, "unassigned": 0, "total": 0}


def test_the_bucket_is_read_only(client, two_projects):
    """Decided deliberately (epic #223, decision 3): tickets are a read-only
    mirror, so nothing assigns one to a project over HTTP."""
    headers = two_projects["headers"]
    response = client.patch(
        "/tickets/ORPHAN-1",
        json={"projectId": two_projects["platform"].id},
        headers=headers,
    )
    assert response.status_code in (404, 405)
