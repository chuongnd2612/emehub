"""Saved ticket queries, the shipped presets, and read-only built-ins.

The two properties worth protecting:

**A built-in is a 409, not a 403.** The caller is not being denied a permission —
the request does not apply to what the row is. The message has to name the way
forward, or read-only presets are a dead end.

**A saved query records its destination.** A query naming `areaPath` cannot run on
Jira and `parentId` has no column in the mirror, so saving one that will be refused
the moment it is applied is worse than refusing to save it: the failure arrives
later, somewhere else, with no clue why.
"""

from __future__ import annotations

import pytest

from app.config import AUDIENCE_QAGENT
from app.services import saved_queries

PASSWORD = "password12345"

ADO_QUERY = {
    "clauses": [{"field": "state", "operator": "in", "values": ["Active", "New"]}],
    "match": "all",
    "sort": {"field": "changedDate", "direction": "desc"},
}


@pytest.fixture
def member(client, make_user, auth_headers):
    make_user("saved@emesoft.net", PASSWORD)
    return auth_headers("saved@emesoft.net", PASSWORD)


@pytest.fixture
def other(client, make_user, auth_headers):
    make_user("saved-other@emesoft.net", PASSWORD)
    return auth_headers("saved-other@emesoft.net", PASSWORD)


def names(rows) -> list[str]:
    return [row["name"] for row in rows]


# ───────────────────────────────────────────────────────────── the presets
def test_the_presets_are_there_and_marked_built_in(client, member):
    rows = client.get("/ticket-queries", headers=member).json()
    assert rows, "no presets were seeded"
    assert all(row["builtIn"] for row in rows if row["shared"])
    assert "Open bugs" in names(rows)


def test_seeding_is_idempotent(client, member, db_session):
    from app.models.ticket_query_saved import SavedTicketQuery

    client.get("/ticket-queries", headers=member)
    first = db_session.query(SavedTicketQuery).count()
    client.get("/ticket-queries", headers=member)
    assert db_session.query(SavedTicketQuery).count() == first


def test_a_corrected_preset_is_updated_in_place(db_session, monkeypatch):
    """Seeded on read rather than in the migration, so fixing a preset's clauses in
    code does not need a data migration chasing it."""
    from app.models.ticket_query_saved import SavedTicketQuery

    saved_queries.seed_built_ins(db_session)
    row = (
        db_session.query(SavedTicketQuery)
        .filter(SavedTicketQuery.name == "Active work")
        .one()
    )
    before = row.id

    fixed = dict(ADO_QUERY)
    monkeypatch.setattr(
        saved_queries, "PRESETS", (("mirror", "Active work", fixed),)
    )
    saved_queries.seed_built_ins(db_session)

    row = db_session.get(SavedTicketQuery, before)
    assert row.query == fixed, "the same row is corrected, not duplicated"


def test_the_state_presets_list_cross_template_spellings():
    """ADO process templates disagree — Agile says Active, Scrum says Committed. A
    preset naming one works in one project and silently returns nothing in the
    next."""
    assert "Active" in saved_queries.ACTIVE_STATES
    assert "Committed" in saved_queries.ACTIVE_STATES
    assert "Doing" in saved_queries.ACTIVE_STATES


def test_the_mirror_presets_avoid_the_assignee_macro():
    """`@Me` resolves at Azure DevOps. Against our own columns it can only be
    matched as a display name, which depends on the provider spelling people the
    way the hub does — so the mirror's presets lean on fields it holds cleanly."""
    for destination, _name, query in saved_queries.PRESETS:
        if destination != "mirror":
            continue
        fields = [clause["field"] for clause in query["clauses"]]
        assert "assignee" not in fields


def test_presets_are_filtered_by_destination(client, member):
    """A query naming areaPath cannot run on Jira, so a caller asks for where it
    intends to run it."""
    mirror = client.get("/ticket-queries?destination=mirror", headers=member).json()
    ado = client.get("/ticket-queries?destination=azure_devops", headers=member).json()
    assert {row["destination"] for row in mirror} == {"mirror"}
    assert {row["destination"] for row in ado} == {"azure_devops"}
    assert "Mine · active now" in names(ado)
    assert "Mine · active now" not in names(mirror)


# ─────────────────────────────────────────────────────────────────── CRUD
def test_save_and_read_back(client, member):
    created = client.post(
        "/ticket-queries",
        json={"name": "My active", "destination": "azure_devops", "query": ADO_QUERY},
        headers=member,
    )
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["builtIn"] is False
    assert body["shared"] is False
    # The description is derived, never taken from the caller.
    assert body["description"] == "state is any of Active or New"

    listed = client.get("/ticket-queries?destination=azure_devops", headers=member).json()
    assert "My active" in names(listed)


def test_the_description_is_re_derived_on_update(client, member):
    created = client.post(
        "/ticket-queries",
        json={"name": "Edit me", "destination": "azure_devops", "query": ADO_QUERY},
        headers=member,
    ).json()

    updated = client.patch(
        f"/ticket-queries/{created['id']}",
        json={"query": {"clauses": [{"field": "title", "operator": "contains", "values": ["boom"]}]}},
        headers=member,
    ).json()
    assert updated["description"] == "title contains boom"


def test_a_query_the_destination_cannot_run_is_refused_before_saving(client, member):
    """Saving one that fails on apply is worse than refusing: the failure arrives
    later, elsewhere, with no clue why."""
    response = client.post(
        "/ticket-queries",
        json={
            "name": "Impossible",
            "destination": "mirror",
            "query": {"clauses": [{"field": "parentId", "operator": "is", "values": ["7"]}]},
        },
        headers=member,
    )
    assert response.status_code == 422
    assert "cannot be filtered" in response.json()["detail"]["problems"][0]["message"]


def test_the_same_name_twice_is_a_conflict(client, member):
    payload = {"name": "Twice", "destination": "azure_devops", "query": ADO_QUERY}
    assert client.post("/ticket-queries", json=payload, headers=member).status_code == 201
    clash = client.post("/ticket-queries", json=payload, headers=member)
    assert clash.status_code == 409
    assert "already saved" in clash.json()["detail"]


def test_delete_removes_it(client, member):
    created = client.post(
        "/ticket-queries",
        json={"name": "Temp", "destination": "mirror", "query": {"clauses": []}},
        headers=member,
    )
    # An empty query is invalid — validation runs before saving.
    assert created.status_code == 422

    created = client.post(
        "/ticket-queries",
        json={"name": "Temp", "destination": "mirror", "query": ADO_QUERY},
        headers=member,
    ).json()
    assert client.delete(f"/ticket-queries/{created['id']}", headers=member).status_code == 200
    assert "Temp" not in names(client.get("/ticket-queries", headers=member).json())


# ──────────────────────────────────────────────────── built-ins are read-only
def _a_builtin(client, headers) -> dict:
    rows = client.get("/ticket-queries", headers=headers).json()
    return next(row for row in rows if row["builtIn"])


def test_editing_a_builtin_is_409_and_names_the_way_forward(client, member):
    """409 rather than 403: the caller is not being denied a permission, the
    request does not apply to what the row is."""
    row = _a_builtin(client, member)
    response = client.patch(
        f"/ticket-queries/{row['id']}", json={"name": "Renamed"}, headers=member
    )
    assert response.status_code == 409
    assert "Duplicate it and edit the copy" in response.json()["detail"]


def test_deleting_a_builtin_is_409(client, member):
    row = _a_builtin(client, member)
    response = client.delete(f"/ticket-queries/{row['id']}", headers=member)
    assert response.status_code == 409
    assert "Duplicate it" in response.json()["detail"]


def test_duplicating_a_builtin_gives_an_editable_copy(client, member):
    """What makes a read-only preset tolerable rather than a dead end."""
    row = _a_builtin(client, member)
    copy = client.post(f"/ticket-queries/{row['id']}/duplicate", headers=member)
    assert copy.status_code == 201, copy.text
    body = copy.json()
    assert body["builtIn"] is False
    assert body["shared"] is False
    assert body["name"] == f"{row['name']} copy"
    assert body["query"] == row["query"]

    # And it really is editable.
    assert client.patch(
        f"/ticket-queries/{body['id']}", json={"name": "Mine now"}, headers=member
    ).status_code == 200


def test_duplicating_twice_does_not_collide(client, member):
    """Duplicating twice is a normal thing to do, so the name is nudged rather than
    the request refused."""
    row = _a_builtin(client, member)
    first = client.post(f"/ticket-queries/{row['id']}/duplicate", headers=member).json()
    second = client.post(f"/ticket-queries/{row['id']}/duplicate", headers=member)
    assert second.status_code == 201, second.text
    assert second.json()["name"] != first["name"]


# ─────────────────────────────────────────────────────────────── scoping
def test_a_members_query_is_invisible_to_another(client, member, other):
    created = client.post(
        "/ticket-queries",
        json={"name": "Private", "destination": "mirror", "query": ADO_QUERY},
        headers=member,
    ).json()

    assert "Private" not in names(client.get("/ticket-queries", headers=other).json())
    # 404, not 403 — a 403 would confirm it exists.
    assert client.patch(
        f"/ticket-queries/{created['id']}", json={"name": "Stolen"}, headers=other
    ).status_code == 404
    assert client.delete(f"/ticket-queries/{created['id']}", headers=other).status_code == 404


def test_a_shared_query_is_visible_to_everyone(client, member, other):
    client.post(
        "/ticket-queries",
        json={"name": "Team query", "destination": "mirror", "query": ADO_QUERY, "shared": True},
        headers=member,
    )
    assert "Team query" in names(client.get("/ticket-queries", headers=other).json())


def test_an_agent_token_may_read_saved_queries(client, make_user, login):
    """CONTRACT posture: an agent that runs queries has the same reason to read a
    saved one."""
    make_user("saved-agent@emesoft.net", PASSWORD)
    token = login("saved-agent@emesoft.net", PASSWORD)["tokens"][AUDIENCE_QAGENT]
    response = client.get("/ticket-queries", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200


def test_saved_queries_require_authentication(client):
    assert client.get("/ticket-queries").status_code == 401
    assert client.post("/ticket-queries", json={}).status_code == 401


def test_a_smuggled_key_is_refused(client, member):
    response = client.post(
        "/ticket-queries",
        json={
            "name": "Sneaky",
            "destination": "mirror",
            "query": ADO_QUERY,
            "wiql": "SELECT 1",
        },
        headers=member,
    )
    assert response.status_code == 422
