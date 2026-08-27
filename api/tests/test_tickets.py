"""The ticket store: reads, paging, filtering and per-owner isolation.

The properties that matter here are the contract ones (INTEGRATION.md §3) plus
the hub-wide scoping rule: a member sees their own tickets and the shared
namespace, and *never* another member's — a ticket belonging to someone else is
indistinguishable from one that does not exist.
"""

from __future__ import annotations

import pytest

from app.config import AUDIENCE_DAGENT, AUDIENCE_QAGENT


@pytest.fixture
def make_ticket(db_session):
    """Insert a ticket row directly, so read tests don't depend on sync."""
    from app.models.ticket import Ticket

    def _make(external_id: str, *, owner=None, **fields):
        ticket = Ticket(
            external_id=external_id,
            provider_kind=fields.pop("provider_kind", "ado"),
            owner_id=(owner.id if owner is not None else None),
            title=fields.pop("title", f"Work item {external_id}"),
            labels=fields.pop("labels", []),
            acceptance_criteria=fields.pop("acceptance_criteria", []),
            comments=fields.pop("comments", []),
            attachments=fields.pop("attachments", []),
            linked_prs=fields.pop("linked_prs", []),
            **fields,
        )
        db_session.add(ticket)
        db_session.commit()
        db_session.refresh(ticket)
        return ticket

    return _make


@pytest.fixture
def make_project(db_session):
    """A real ``projects`` row. ``tickets.project_id`` is a FK since #217, so a
    made-up id is no longer insertable — the constraint is the point."""
    from app.models.project import Project

    def _make(key: str, *, owner=None, name: str = ""):
        row = Project(
            key=key, name=name or key, owner_id=(owner.id if owner is not None else None)
        )
        db_session.add(row)
        db_session.commit()
        db_session.refresh(row)
        return row

    return _make


@pytest.fixture
def member(client, make_user, auth_headers):
    user = make_user("member@emesoft.net", "password12345")
    return user, auth_headers("member@emesoft.net", "password12345")


# ---------------------------------------------------------------- auth posture
def test_tickets_require_authentication(client):
    assert client.get("/tickets").status_code == 401
    assert client.get("/tickets/SUR-1").status_code == 401
    assert client.post("/tickets/sync", json={}).status_code == 401
    assert client.delete("/tickets/SUR-1").status_code == 401


def test_an_agent_token_may_read_the_store(client, make_user, login, make_ticket):
    """CONTRACT posture: agents call with their own audience, not a hub token."""
    user = make_user("agentread@emesoft.net", "password12345")
    make_ticket("SUR-1", owner=user)
    tokens = login("agentread@emesoft.net", "password12345")["tokens"]

    for audience in (AUDIENCE_QAGENT, AUDIENCE_DAGENT):
        headers = {"Authorization": f"Bearer {tokens[audience]}"}
        listed = client.get("/tickets", headers=headers)
        assert listed.status_code == 200, listed.text
        assert [t["externalId"] for t in listed.json()["items"]] == ["SUR-1"]
        assert client.get("/tickets/SUR-1", headers=headers).status_code == 200


def test_an_unregistered_audience_is_still_refused(client, make_user, login, monkeypatch):
    import app.config as config_module

    make_user("dereg-t@emesoft.net", "password12345")
    dagent = login("dereg-t@emesoft.net", "password12345")["tokens"][AUDIENCE_DAGENT]
    monkeypatch.setattr(config_module.settings, "agent_dagent_url", "")
    response = client.get("/tickets", headers={"Authorization": f"Bearer {dagent}"})
    assert response.status_code == 401


# ---------------------------------------------------------------- listing
def test_list_returns_the_camel_case_contract_shape(client, member, make_ticket):
    user, headers = member
    make_ticket(
        "SUR-1428",
        owner=user,
        title="Eligibility import",
        work_item_type="Bug",
        status="Ready for QA",
        priority="High",
        assignee="duna",
        sprint="Sprint 12",
        area_path="Surency\\Data Platform",
        epic="Imports",
        labels=["backend"],
        acceptance_criteria=["a", "b"],
    )

    body = client.get("/tickets", headers=headers).json()
    assert body["total"] == 1
    assert body["page"] == 1 and body["pageSize"] == 25
    item = body["items"][0]
    assert item["externalId"] == "SUR-1428"
    assert item["providerKind"] == "ado"
    assert item["workItemType"] == "Bug"
    assert item["areaPath"] == "Surency\\Data Platform"
    assert item["acCount"] == 2
    assert item["syncedAt"]


def test_paging_splits_the_result_and_keeps_the_total(client, member, make_ticket):
    user, headers = member
    for n in range(1, 8):
        make_ticket(f"SUR-{n}", owner=user)

    first = client.get("/tickets?page=1&pageSize=3", headers=headers).json()
    second = client.get("/tickets?page=2&pageSize=3", headers=headers).json()
    third = client.get("/tickets?page=3&pageSize=3", headers=headers).json()

    assert first["total"] == second["total"] == third["total"] == 7
    assert len(first["items"]) == len(second["items"]) == 3
    assert len(third["items"]) == 1
    ids = [t["externalId"] for page in (first, second, third) for t in page["items"]]
    assert len(set(ids)) == 7  # no row appears on two pages


def test_paging_beyond_the_end_is_an_empty_page_not_an_error(client, member, make_ticket):
    user, headers = member
    make_ticket("SUR-1", owner=user)
    body = client.get("/tickets?page=9&pageSize=10", headers=headers).json()
    assert body["items"] == [] and body["total"] == 1


def test_filter_by_project(client, member, make_ticket, make_project):
    user, headers = member
    shop = make_project("shop", owner=user)
    depot = make_project("depot", owner=user)
    make_ticket("SUR-1", owner=user, project_id=shop.id)
    make_ticket("SUR-2", owner=user, project_id=depot.id)
    make_ticket("SUR-3", owner=user)  # unattributed

    body = client.get(f"/tickets?projectId={shop.id}", headers=headers).json()
    assert [t["externalId"] for t in body["items"]] == ["SUR-1"]
    assert body["total"] == 1


def test_filter_by_provider(client, member, make_ticket):
    user, headers = member
    make_ticket("SUR-1", owner=user, provider_kind="ado")
    make_ticket("JRA-1", owner=user, provider_kind="jira")

    body = client.get("/tickets?providerKind=jira", headers=headers).json()
    assert [t["externalId"] for t in body["items"]] == ["JRA-1"]


def test_the_remaining_filters_narrow_the_page(client, member, make_ticket):
    user, headers = member
    make_ticket(
        "SUR-1",
        owner=user,
        status="Done",
        assignee="duna",
        sprint="S1",
        priority="High",
        epic="Imports",
        work_item_type="Bug",
        area_path="Surency\\Data Platform",
        connection_id=7,
    )
    make_ticket(
        "SUR-2",
        owner=user,
        status="Blocked",
        assignee="linh",
        sprint="S2",
        priority="Low",
        epic="Reports",
        work_item_type="User Story",
        area_path="Surency\\Web",
        connection_id=8,
    )

    def ids(query: str) -> list[str]:
        body = client.get(f"/tickets?{query}", headers=headers).json()
        return [t["externalId"] for t in body["items"]]

    assert ids("status=Done") == ["SUR-1"]
    assert ids("assignee=linh") == ["SUR-2"]
    assert ids("sprint=S1") == ["SUR-1"]
    assert ids("priority=Low") == ["SUR-2"]
    assert ids("epic=Imports") == ["SUR-1"]
    assert ids("connectionId=8") == ["SUR-2"]
    assert ids("workItemTypes=Bug,Task") == ["SUR-1"]
    assert sorted(ids("states=Done,Blocked")) == ["SUR-1", "SUR-2"]
    assert ids("q=SUR-2") == ["SUR-2"]
    # Backslashes in an ADO area path must survive the LIKE, not be eaten as
    # escape characters.
    assert ids("areaPath=Surency%5CData") == ["SUR-1"]


# ---------------------------------------------------------------- lookup
def test_lookup_by_external_id_returns_the_full_detail(client, member, make_ticket):
    user, headers = member
    make_ticket(
        "SUR-1428",
        owner=user,
        description="<p>Import fails</p>",
        acceptance_criteria=["Given a file", "Then it imports"],
        acceptance_criteria_html="<ol><li>Given a file</li></ol>",
        comments=[{"who": "duna", "when": "2h ago", "text": "looking"}],
        attachments=[{"name": "log.txt", "size": "2048"}],
        linked_prs=[
            {
                "repo": "surency-etl",
                "num": "42",
                "title": "Fix the import",
                "status": "Active",
                "url": "https://dev.azure.com/emesoft/_git/surency-etl/pullrequest/42",
            }
        ],
    )

    body = client.get("/tickets/SUR-1428", headers=headers).json()
    assert body["externalId"] == "SUR-1428"
    assert body["description"] == "<p>Import fails</p>"
    assert body["acceptanceCriteria"] == ["Given a file", "Then it imports"]
    assert body["acceptanceCriteriaHtml"] == "<ol><li>Given a file</li></ol>"
    assert body["comments"] == [{"who": "duna", "when": "2h ago", "text": "looking"}]
    assert body["attachments"] == [{"name": "log.txt", "size": "2048"}]
    assert body["linkedPrs"] == [
        {
            "repo": "surency-etl",
            "num": "42",
            "title": "Fix the import",
            "status": "Active",
            "url": "https://dev.azure.com/emesoft/_git/surency-etl/pullrequest/42",
        }
    ]


def test_a_partial_stored_nested_row_normalises_rather_than_500ing(
    client, member, make_ticket
):
    """The three nested lists are typed, and the typing must not be a gate.

    These dicts were written by adapters over time and out of the hub's control,
    so a row missing a key — or carrying one the adapter has since stopped
    emitting — has to come back with the missing fields as `""` and the unknown
    ones dropped. Failing the read instead would make a detail page unopenable
    because of a field it does not even show.
    """
    user, headers = member
    make_ticket(
        "SUR-99",
        owner=user,
        comments=[{"who": "duna"}, {"text": "no author", "legacyId": 7}],
        attachments=[{"name": "log.txt"}],
        linked_prs=[{"num": "42"}],
    )

    body = client.get("/tickets/SUR-99", headers=headers)
    assert body.status_code == 200, body.text
    detail = body.json()
    assert detail["comments"] == [
        {"who": "duna", "when": "", "text": ""},
        {"who": "", "when": "", "text": "no author"},
    ]
    assert detail["attachments"] == [{"name": "log.txt", "size": ""}]
    assert detail["linkedPrs"] == [
        {"repo": "", "num": "42", "title": "", "status": "", "url": ""}
    ]


def test_the_provider_url_is_on_both_the_list_and_the_detail(client, member, make_ticket):
    """INTEGRATION.md §3 › *The work item's own URL*.

    On the LIST too, not only the detail: a consumer rendering a table of work
    items would otherwise need one detail request per row to link any of them.
    """
    user, headers = member
    make_ticket(
        "SUR-1428",
        owner=user,
        url="https://dev.azure.com/emesoft/Surency/_workitems/edit/1428",
    )

    listed = client.get("/tickets", headers=headers).json()["items"][0]
    detail = client.get("/tickets/SUR-1428", headers=headers).json()
    assert listed["url"] == detail["url"] == (
        "https://dev.azure.com/emesoft/Surency/_workitems/edit/1428"
    )


def test_a_ticket_with_no_provider_url_answers_empty_not_absent(client, member, make_ticket):
    """`""` is "no link to offer" — a present, empty field, so a consumer can
    branch on it without treating a missing key as a schema change."""
    user, headers = member
    make_ticket("SUR-9", owner=user)

    detail = client.get("/tickets/SUR-9", headers=headers).json()
    assert "url" in detail and detail["url"] == ""


def test_lookup_of_an_unknown_id_is_404(client, member):
    _, headers = member
    assert client.get("/tickets/NOPE-1", headers=headers).status_code == 404


def test_lookup_can_disambiguate_by_provider(client, member, make_ticket):
    """The same external id may exist in two providers."""
    user, headers = member
    make_ticket("1428", owner=user, provider_kind="ado", title="ADO copy")
    make_ticket("1428", owner=user, provider_kind="jira", title="Jira copy")

    assert client.get("/tickets/1428?providerKind=jira", headers=headers).json()["title"] == (
        "Jira copy"
    )
    assert client.get("/tickets/1428?providerKind=ado", headers=headers).json()["title"] == (
        "ADO copy"
    )


# ---------------------------------------------------------------- isolation
def test_a_member_never_sees_another_members_tickets(client, make_user, auth_headers, make_ticket):
    alice = make_user("alice@emesoft.net", "password12345")
    bob = make_user("bob@emesoft.net", "password12345")
    make_ticket("ALICE-1", owner=alice)
    make_ticket("BOB-1", owner=bob)
    make_ticket("SHARED-1", owner=None)  # NULL owner == the shared namespace

    for email, own in (("alice@emesoft.net", "ALICE-1"), ("bob@emesoft.net", "BOB-1")):
        headers = auth_headers(email, "password12345")
        body = client.get("/tickets", headers=headers).json()
        assert sorted(t["externalId"] for t in body["items"]) == sorted([own, "SHARED-1"])
        assert body["total"] == 2


def test_another_members_ticket_404s_rather_than_403s(client, make_user, auth_headers, make_ticket):
    """A 403 would confirm the row exists, which is itself a disclosure."""
    alice = make_user("alice2@emesoft.net", "password12345")
    make_user("bob2@emesoft.net", "password12345")
    make_ticket("ALICE-9", owner=alice)

    headers = auth_headers("bob2@emesoft.net", "password12345")
    assert client.get("/tickets/ALICE-9", headers=headers).status_code == 404
    assert client.delete("/tickets/ALICE-9", headers=headers).status_code == 404


def test_an_admin_is_not_a_way_around_per_owner_isolation(
    client, make_user, auth_headers, make_ticket
):
    """Ownership is not a permission — being an admin does not reveal a
    member's private rows (``ownership.owned`` has no role branch)."""
    alice = make_user("alice3@emesoft.net", "password12345")
    make_user("root@emesoft.net", "password12345", role="admin")
    make_ticket("ALICE-3", owner=alice)

    headers = auth_headers("root@emesoft.net", "password12345")
    assert client.get("/tickets", headers=headers).json()["items"] == []
    assert client.get("/tickets/ALICE-3", headers=headers).status_code == 404


def test_a_filter_cannot_widen_the_scope(
    client, make_user, auth_headers, make_ticket, make_project
):
    alice = make_user("alice4@emesoft.net", "password12345")
    make_user("bob4@emesoft.net", "password12345")
    project = make_project("alice-shop", owner=alice)
    make_ticket("ALICE-4", owner=alice, provider_kind="jira", project_id=project.id)

    headers = auth_headers("bob4@emesoft.net", "password12345")
    for query in ("providerKind=jira", f"projectId={project.id}", "q=ALICE"):
        body = client.get(f"/tickets?{query}", headers=headers).json()
        assert body["items"] == [] and body["total"] == 0


# ---------------------------------------------------------------- delete
def test_delete_removes_only_the_callers_own_row(client, member, make_ticket, db_session):
    from app.models.ticket import Ticket

    user, headers = member
    make_ticket("SUR-1", owner=user)

    assert client.delete("/tickets/SUR-1", headers=headers).status_code == 204
    assert db_session.query(Ticket).filter(Ticket.external_id == "SUR-1").count() == 0
    assert client.delete("/tickets/SUR-1", headers=headers).status_code == 404


def test_delete_is_audited_as_a_ticket_event(client, member, make_ticket, db_session):
    from app.models.audit import AuditLog

    user, headers = member
    make_ticket("SUR-77", owner=user)
    client.delete("/tickets/SUR-77", headers=headers)

    event = (
        db_session.query(AuditLog)
        .filter(AuditLog.category == "ticket", AuditLog.target == "SUR-77")
        .one()
    )
    assert event.action == "Removed ticket"
    assert event.actor_id == user.id


# ---------------------------------------------------------------- schema
def test_the_migration_created_the_tickets_table(workspace_dir):
    from sqlalchemy import inspect

    import app.db as db_module

    inspector = inspect(db_module.engine)
    assert "tickets" in inspector.get_table_names()
    columns = {c["name"] for c in inspector.get_columns("tickets")}
    assert {
        "external_id",
        "provider_kind",
        "project_id",
        "connection_id",
        "title",
        "work_item_type",
        "status",
        "priority",
        "assignee",
        "sprint",
        "area_path",
        "epic",
        "description",
        "labels",
        "acceptance_criteria",
        "acceptance_criteria_html",
        "comments",
        "attachments",
        "linked_prs",
        "url",
        "synced_at",
        "owner_id",
    } <= columns
