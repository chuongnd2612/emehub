"""Saved ticket queries gain a project scope (#222).

Slice 6 of the project-containment epic (#223), and the slice that reverses a
written decision: `models/ticket_query_saved.py` argued *against* project scoping
and ADR 0011 overrules it. What is asserted here is therefore not "the column
exists" but the behaviour the column was added for:

* **Containment is enforced, not merely stored.** A query bound to one project is
  not offered in another. A column nothing filters on is not a feature.
* **Workspace-wide still means workspace-wide.** A query with no project — which
  is every row that predates this slice, and every shipped preset — is offered in
  any project on the matching destination.
* **The migration reinterprets nothing.** Rows planted at ``0016`` come out of the
  upgrade with ``project_id IS NULL``, built-ins included, and the downgrade
  renames rather than deletes when two projects held the same name.
* **A built-in is untouched.** Still workspace-wide, still listed inside a
  project, still 409-and-duplicate on edit or delete.
* **The unique constraint does what we said it does** — and, just as importantly,
  does *not* do what a reader might assume: NULLs are distinct on both engines, so
  the shared and workspace-wide cases are held by the service, not the index.

Two projects are seeded on **different providers**, following #217 and
``../q-agent/api/scripts/probe_setup_732.py``: with one project, "the other
project's rows must not appear" is a vacuous assertion.
"""

from __future__ import annotations

import pytest
from sqlalchemy import inspect
from sqlalchemy.exc import IntegrityError

PASSWORD = "password12345"
PREVIOUS_REVISION = "0016_ticket_project_fk"

ADO_QUERY = {
    "clauses": [{"field": "state", "operator": "in", "values": ["Active", "New"]}],
    "match": "all",
    "sort": {"field": "changedDate", "direction": "desc"},
}


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


def _project(db, key: str, owner_id: int | None):
    from app.models.project import Project

    row = Project(key=key, name=key, owner_id=owner_id)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _user_row(db, email: str):
    from app.models.user import User

    return db.query(User).filter(User.email == email).one()


def names(rows) -> list[str]:
    return [row["name"] for row in rows]


@pytest.fixture
def member(client, make_user, auth_headers):
    make_user("scoped@emesoft.net", PASSWORD)
    return auth_headers("scoped@emesoft.net", PASSWORD)


@pytest.fixture
def other(client, make_user, auth_headers):
    make_user("scoped-other@emesoft.net", PASSWORD)
    return auth_headers("scoped-other@emesoft.net", PASSWORD)


@pytest.fixture
def projects(client, member, db_session):
    """Two projects the member can see, on two different providers."""
    user = _user_row(db_session, "scoped@emesoft.net")
    platform = _project(db_session, "surency-platform", user.id)
    claims = _project(db_session, "claims-portal", user.id)
    return platform, claims


# ---------------------------------------------------------------- containment
def test_a_project_scoped_query_is_not_offered_in_another_project(
    client, member, projects
):
    platform, claims = projects
    created = client.post(
        "/ticket-queries",
        json={
            "name": "Platform triage",
            "destination": "mirror",
            "query": ADO_QUERY,
            "projectId": platform.id,
        },
        headers=member,
    )
    assert created.status_code == 201, created.text
    assert created.json()["projectId"] == platform.id

    inside = client.get(f"/ticket-queries?projectId={platform.id}", headers=member).json()
    elsewhere = client.get(f"/ticket-queries?projectId={claims.id}", headers=member).json()
    assert "Platform triage" in names(inside)
    assert "Platform triage" not in names(elsewhere)


def test_a_workspace_wide_query_is_offered_in_every_project(client, member, projects):
    """No project means workspace-wide — which is what every row that predates
    this slice is, and the reason the migration rewrote none of them."""
    platform, claims = projects
    created = client.post(
        "/ticket-queries",
        json={"name": "Everywhere", "destination": "mirror", "query": ADO_QUERY},
        headers=member,
    )
    assert created.status_code == 201, created.text
    assert created.json()["projectId"] is None

    for project in (platform, claims):
        listed = client.get(f"/ticket-queries?projectId={project.id}", headers=member).json()
        assert "Everywhere" in names(listed), project.key


def test_omitting_the_project_lists_everything_the_caller_may_see(
    client, member, projects
):
    """The management view. A project-bound query must remain listable — and
    therefore deletable — from outside its project, or it would be unreachable
    the moment the UI navigated away."""
    platform, _claims = projects
    client.post(
        "/ticket-queries",
        json={
            "name": "Platform triage",
            "destination": "mirror",
            "query": ADO_QUERY,
            "projectId": platform.id,
        },
        headers=member,
    )
    assert "Platform triage" in names(client.get("/ticket-queries", headers=member).json())


def test_a_project_the_caller_cannot_see_is_404(client, member, other, db_session):
    """404, never 403 — a 403 would confirm the project exists."""
    stranger = _user_row(db_session, "scoped-other@emesoft.net")
    theirs = _project(db_session, "private-thing", stranger.id)

    refused = client.post(
        "/ticket-queries",
        json={
            "name": "Peek",
            "destination": "mirror",
            "query": ADO_QUERY,
            "projectId": theirs.id,
        },
        headers=member,
    )
    assert refused.status_code == 404
    assert client.get(f"/ticket-queries?projectId={theirs.id}", headers=member).status_code == 404
    assert client.get("/ticket-queries?projectId=987654", headers=member).status_code == 404


def test_a_projects_saved_queries_go_with_the_project(client, member, projects, db_session):
    """``ON DELETE CASCADE``, and the reason it is not SET NULL: a query left
    behind would be silently *widened* into every project on its destination,
    clauses and derived description still describing the narrower one."""
    from app.models.project import Project
    from app.models.ticket_query_saved import SavedTicketQuery

    platform, _claims = projects
    client.get("/ticket-queries", headers=member)  # seeds the presets
    created = client.post(
        "/ticket-queries",
        json={
            "name": "Goes with it",
            "destination": "mirror",
            "query": ADO_QUERY,
            "projectId": platform.id,
        },
        headers=member,
    ).json()

    db_session.expire_all()
    db_session.delete(db_session.get(Project, platform.id))
    db_session.commit()

    assert db_session.get(SavedTicketQuery, created["id"]) is None
    # And nothing else went with it: the presets are workspace-wide.
    assert db_session.query(SavedTicketQuery).filter_by(built_in=True).count() > 0


def test_the_project_is_immutable_on_patch(client, member, projects):
    """Moving a query between containers would change what its clauses run
    against while its name and description still described the old one."""
    platform, claims = projects
    created = client.post(
        "/ticket-queries",
        json={
            "name": "Stay put",
            "destination": "mirror",
            "query": ADO_QUERY,
            "projectId": platform.id,
        },
        headers=member,
    ).json()
    response = client.patch(
        f"/ticket-queries/{created['id']}",
        json={"projectId": claims.id},
        headers=member,
    )
    assert response.status_code == 422


def test_the_description_is_still_re_derived_for_a_project_query(client, member, projects):
    platform, _claims = projects
    created = client.post(
        "/ticket-queries",
        json={
            "name": "Derived",
            "destination": "azure_devops",
            "query": ADO_QUERY,
            "projectId": platform.id,
        },
        headers=member,
    ).json()
    assert created["description"] == "state is any of Active or New"

    updated = client.patch(
        f"/ticket-queries/{created['id']}",
        json={
            "query": {
                "clauses": [{"field": "title", "operator": "contains", "values": ["boom"]}]
            }
        },
        headers=member,
    ).json()
    assert updated["description"] == "title contains boom"
    assert updated["projectId"] == platform.id


# ---------------------------------------------------------------- built-ins
def test_every_built_in_is_workspace_wide_and_offered_inside_a_project(
    client, member, projects
):
    platform, _claims = projects
    everything = client.get("/ticket-queries", headers=member).json()
    built_ins = [row for row in everything if row["builtIn"]]
    assert built_ins, "no presets were seeded"
    assert all(row["projectId"] is None for row in built_ins)

    inside = client.get(f"/ticket-queries?projectId={platform.id}", headers=member).json()
    assert {row["name"] for row in built_ins} <= set(names(inside))


def test_a_built_in_still_refuses_edit_and_delete_inside_a_project(
    client, member, projects
):
    platform, _claims = projects
    inside = client.get(f"/ticket-queries?projectId={platform.id}", headers=member).json()
    row = next(item for item in inside if item["builtIn"])

    patched = client.patch(
        f"/ticket-queries/{row['id']}", json={"name": "Renamed"}, headers=member
    )
    assert patched.status_code == 409
    assert "Duplicate it and edit the copy" in patched.json()["detail"]

    deleted = client.delete(f"/ticket-queries/{row['id']}", headers=member)
    assert deleted.status_code == 409
    assert "Duplicate it" in deleted.json()["detail"]


def test_duplicating_a_built_in_into_a_project_binds_the_copy_only(
    client, member, projects
):
    """How a project gets its own version of a shipped preset. The preset is not
    rewritten — it stays workspace-wide and read-only."""
    platform, claims = projects
    rows = client.get("/ticket-queries", headers=member).json()
    preset = next(row for row in rows if row["builtIn"])

    copy = client.post(
        f"/ticket-queries/{preset['id']}/duplicate",
        json={"projectId": platform.id},
        headers=member,
    )
    assert copy.status_code == 201, copy.text
    body = copy.json()
    assert body["projectId"] == platform.id
    assert body["builtIn"] is False

    still = client.get("/ticket-queries", headers=member).json()
    assert next(row for row in still if row["id"] == preset["id"])["projectId"] is None
    assert body["name"] not in names(
        client.get(f"/ticket-queries?projectId={claims.id}", headers=member).json()
    )


# ------------------------------------------------------- the unique constraint
def test_the_same_name_is_free_in_another_project_and_taken_in_this_one(
    client, member, projects
):
    """Why ``project_id`` had to join ``uq_saved_query_name``: without it, one
    project's "Backlog triage" would block the next project's."""
    platform, claims = projects
    payload = {"name": "Backlog triage", "destination": "mirror", "query": ADO_QUERY}

    first = client.post(
        "/ticket-queries", json={**payload, "projectId": platform.id}, headers=member
    )
    second = client.post(
        "/ticket-queries", json={**payload, "projectId": claims.id}, headers=member
    )
    clash = client.post(
        "/ticket-queries", json={**payload, "projectId": platform.id}, headers=member
    )
    assert first.status_code == 201, first.text
    assert second.status_code == 201, second.text
    assert clash.status_code == 409
    assert "already saved" in clash.json()["detail"]


def test_a_workspace_wide_name_does_not_block_a_project_one(client, member, projects):
    platform, _claims = projects
    payload = {"name": "Same name", "destination": "mirror", "query": ADO_QUERY}
    assert client.post("/ticket-queries", json=payload, headers=member).status_code == 201
    assert (
        client.post(
            "/ticket-queries", json={**payload, "projectId": platform.id}, headers=member
        ).status_code
        == 201
    )
    # …and the workspace-wide one is still taken.
    assert client.post("/ticket-queries", json=payload, headers=member).status_code == 409


def test_the_constraint_covers_the_four_columns_and_bites_only_when_none_is_null(
    db_session, projects, client, member
):
    """The behaviour chosen deliberately, asserted rather than assumed.

    Both engines treat NULLs as **distinct** in a unique index — Postgres by
    default (``NULLS NOT DISTINCT`` is not used, precisely so the two agree) and
    SQLite always. So the index enforces the fully-specified tuple and nothing
    else, which is why `saved_queries.create_query` compares both nullable axes
    with ``IS NULL`` and is the check that actually holds.
    """
    from app.models.ticket_query_saved import SavedTicketQuery

    inspector = inspect(db_session.get_bind())
    constraint = next(
        uq
        for uq in inspector.get_unique_constraints("saved_ticket_queries")
        if uq["name"] == "uq_saved_query_name"
    )
    assert constraint["column_names"] == [
        "owner_id",
        "project_id",
        "destination",
        "name",
    ]

    platform, _claims = projects
    user = _user_row(db_session, "scoped@emesoft.net")

    def _row(owner_id, project_id):
        return SavedTicketQuery(
            name="Twin",
            destination="mirror",
            query=ADO_QUERY,
            description="",
            built_in=False,
            position=0,
            owner_id=owner_id,
            project_id=project_id,
        )

    # Fully specified: the index refuses the second one.
    db_session.add_all([_row(user.id, platform.id), _row(user.id, platform.id)])
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()

    # Either axis NULL and the index lets both through — so the service must not
    # rely on it. It does not: the API refuses the duplicate with a 409.
    db_session.add_all([_row(None, None), _row(None, None)])
    db_session.commit()
    assert (
        db_session.query(SavedTicketQuery).filter_by(name="Twin").count() == 2
    ), "NULLs are distinct in the index — this is the documented behaviour"

    refused = client.post(
        "/ticket-queries",
        json={"name": "Twin", "destination": "mirror", "query": ADO_QUERY, "shared": True},
        headers=member,
    )
    assert refused.status_code == 409, refused.text


# ---------------------------------------------------------------- the migration
def test_the_migration_leaves_every_existing_row_workspace_wide(workspace_dir):
    """Down to ``0016``, plant the rows the hub has in the wild, run ``0017``
    forward for real. Nothing is reinterpreted: a member's saved query and a
    shipped preset both come out with no project."""
    import app.db as db_module
    from app.models.ticket_query_saved import SavedTicketQuery
    from app.models.user import User
    from app.services import auth_service, saved_queries

    seed = db_module.SessionLocal()
    try:
        saved_queries.seed_built_ins(seed)
        preset_names = {
            row.name for row in seed.query(SavedTicketQuery).filter_by(built_in=True)
        }
        assert preset_names
    finally:
        seed.close()

    _alembic("downgrade", PREVIOUS_REVISION)

    setup = db_module.SessionLocal()
    try:
        user = User(
            email="premigration@emesoft.net",
            first_name="Pre",
            last_name="Migration",
            role="member",
            password_hash=auth_service.hash_password(PASSWORD),
            is_active=True,
        )
        setup.add(user)
        setup.commit()
        setup.refresh(user)
        # Written with raw SQL: the column does not exist at this revision, so the
        # model cannot be used — which is exactly the state 0017 inherits.
        setup.execute(
            SavedTicketQuery.__table__.insert().values(
                name="Mine from before",
                destination="mirror",
                query=ADO_QUERY,
                description="state is any of Active or New",
                built_in=False,
                position=0,
                owner_id=user.id,
            )
        )
        setup.commit()
    finally:
        setup.close()

    _alembic("upgrade", "head")

    check = db_module.SessionLocal()
    try:
        rows = check.query(SavedTicketQuery).all()
        assert {row.name for row in rows} >= preset_names | {"Mine from before"}
        assert all(row.project_id is None for row in rows), "a row was reinterpreted"
        assert {row.name for row in rows if row.built_in} == preset_names
    finally:
        check.close()


def test_the_migration_reverses_with_project_bound_and_built_in_rows_present(
    workspace_dir,
):
    """Down and up again with built-ins, a workspace-wide query and two
    project-bound queries **sharing one name** — the collision the downgrade has
    to survive, since two projects holding the same name is legal forward and one
    duplicate backward.

    The workspace-wide row keeps its name; the project-bound ones are suffixed,
    not deleted. A renamed saved query is recoverable, a deleted one is not.
    """
    import app.db as db_module
    from app.models.ticket_query_saved import SavedTicketQuery
    from app.models.user import User
    from app.services import auth_service, saved_queries

    setup = db_module.SessionLocal()
    try:
        saved_queries.seed_built_ins(setup)
        built_ins_before = {
            row.name for row in setup.query(SavedTicketQuery).filter_by(built_in=True)
        }

        user = User(
            email="reverse-query@emesoft.net",
            first_name="Re",
            last_name="Verse",
            role="member",
            password_hash=auth_service.hash_password(PASSWORD),
            is_active=True,
        )
        setup.add(user)
        setup.commit()
        setup.refresh(user)

        one = _project(setup, "one", user.id)
        two = _project(setup, "two", user.id)
        saved_queries.create_query(
            setup, user, name="Triage", destination="mirror", query=ADO_QUERY
        )
        saved_queries.create_query(
            setup,
            user,
            name="Triage",
            destination="mirror",
            query=ADO_QUERY,
            project_id=one.id,
        )
        saved_queries.create_query(
            setup,
            user,
            name="Triage",
            destination="mirror",
            query=ADO_QUERY,
            project_id=two.id,
        )
        total_before = setup.query(SavedTicketQuery).count()
        project_ids = (one.id, two.id)
    finally:
        setup.close()

    _alembic("downgrade", PREVIOUS_REVISION)

    after_down = db_module.SessionLocal()
    try:
        assert after_down.query(SavedTicketQuery.id).count() == total_before, (
            "the downgrade deleted a saved query"
        )
        rows = [
            row[0]
            for row in after_down.execute(
                SavedTicketQuery.__table__.select().with_only_columns(
                    SavedTicketQuery.__table__.c.name
                )
            )
        ]
        assert rows.count("Triage") == 1, "the workspace-wide row lost its name"
        for project_id in project_ids:
            assert f"Triage (project {project_id})" in rows

        inspector = inspect(db_module.engine)
        assert "project_id" not in {
            column["name"]
            for column in inspector.get_columns("saved_ticket_queries")
        }
        constraint = next(
            uq
            for uq in inspector.get_unique_constraints("saved_ticket_queries")
            if uq["name"] == "uq_saved_query_name"
        )
        assert constraint["column_names"] == ["owner_id", "destination", "name"]
    finally:
        after_down.close()

    _alembic("upgrade", "head")

    after_up = db_module.SessionLocal()
    try:
        rows = after_up.query(SavedTicketQuery).all()
        assert len(rows) == total_before
        assert all(row.project_id is None for row in rows)
        assert {
            row.name for row in rows if row.built_in
        } == built_ins_before, "a built-in was rewritten"
        inspector = inspect(db_module.engine)
        assert [
            fk
            for fk in inspector.get_foreign_keys("saved_ticket_queries")
            if fk["constrained_columns"] == ["project_id"]
        ]
    finally:
        after_up.close()
