"""Ticket sync, driven entirely through the injected source seam.

Sync's only dependency on the provider-adapter layer is
``ticket_service.TicketSource`` — one method, the same signature as
``ProviderAdapter.fetch_tickets``. These tests inject a fake through
``use_ticket_source_resolver``, so the store's sync behaviour (upsert, scoping,
stamping, failure mapping) is verified without any adapter existing.
"""

from __future__ import annotations

import pytest

from app.services import ticket_service


class FakeSource:
    """A :class:`ticket_service.TicketSource`. Records the selection it was
    called with so the tests can assert the request reached the provider."""

    def __init__(self, batches: list[list[dict]] | None = None) -> None:
        self.batches = list(batches or [])
        self.calls: list[dict] = []

    def fetch_tickets(self, **selection):
        self.calls.append(selection)
        return self.batches.pop(0) if self.batches else []


def resolver_for(source, *, provider_kind="ado", connection_id=7, label="ADO — Surency"):
    def _resolve(db, user, requested_connection_id, requested_provider_kind):
        return ticket_service.ResolvedSource(
            source=source,
            provider_kind=requested_provider_kind or provider_kind,
            connection_id=requested_connection_id or connection_id,
            label=label,
        )

    return _resolve


@pytest.fixture
def member(client, make_user, auth_headers):
    user = make_user("syncer@emesoft.net", "password12345")
    return user, auth_headers("syncer@emesoft.net", "password12345")


#: A clause query, for the tests that are about queries.
QUERY = {
    "clauses": [{"field": "state", "operator": "is", "values": ["Active"]}],
    "match": "all",
    "sort": {"field": "changedDate", "direction": "desc"},
}

#: What to pull, for the tests that are about the STORE rather than the selection.
#: Named ids rather than a query: they need `sync` to reach the source at all, and
#: an id list is the selection that needs no destination to validate against.
PULL = {"ticketIds": ["SUR-1428"]}

ITEM = {
    "external_id": "SUR-1428",
    "title": "Eligibility import fails",
    "work_item_type": "Bug",
    "status": "Ready for QA",
    "priority": "High",
    "assignee": "duna",
    "sprint": "Sprint 12",
    "area_path": "Surency\\Data Platform",
    "epic": "Imports",
    "description": "<p>boom</p>",
    "labels": ["backend"],
    "acceptance_criteria": ["Given a file", "Then it imports"],
    "acceptance_criteria_html": "<ol><li>Given a file</li></ol>",
    "comments": [{"author": "duna"}],
    "attachments": [{"name": "log.txt"}],
    "linked_prs": [{"id": 42}],
    "url": "https://dev.azure.com/emesoft/Surency/_workitems/edit/1428",
    # QAgent's local QA annotation. The hub does not store it — asserted below.
    "note": "ignore me",
}


# ---------------------------------------------------------------- the seam
def test_the_fake_satisfies_the_declared_protocol():
    """If this fails, the fake and the real adapter have drifted apart."""
    assert isinstance(FakeSource(), ticket_service.TicketSource)


def test_the_seam_is_resolved_at_call_time_not_import_time(client, member):
    """Injection has to work after the router module was imported."""
    _, headers = member
    source = FakeSource([[ITEM]])
    with ticket_service.use_ticket_source_resolver(resolver_for(source)):
        assert (
            client.post("/tickets/sync", json={"providerKind": "ado", **PULL}, headers=headers).json()[
                "synced"
            ]
            == 1
        )
    # …and the default is restored on exit.
    assert ticket_service._resolver is ticket_service._resolve_from_adapters


def test_the_default_resolver_reaches_the_real_connections_layer(client, member):
    """The seam is wired to the adapters.

    This test used to assert a 503, because ``app.services.adapters`` did not
    exist while tickets and connections were built in parallel. It does now, so
    the default resolver imports cleanly and gets as far as looking for a
    connection — and with none configured that is a 404, not a 503 ("the layer
    is missing") and never a 200 with zero tickets.
    """
    _, headers = member
    response = client.post("/tickets/sync", json={"providerKind": "ado", **PULL}, headers=headers)
    assert response.status_code == 404
    detail = response.json()["detail"]
    assert "connection" in detail.lower()
    assert "not available in this deployment" not in detail


def test_a_query_is_passed_through_to_the_source(client, member):
    _, headers = member
    source = FakeSource([[]])
    with ticket_service.use_ticket_source_resolver(resolver_for(source)):
        client.post(
            "/tickets/sync",
            json={
                "connectionId": 3,
                "providerKind": "azure_devops",
                "project": "Surency",
                "query": QUERY,
            },
            headers=headers,
        )
    call = source.calls[0]
    assert call["project"] == "Surency"
    assert call["spec"].clauses[0].field == "state"
    # Comments are an N+1 during bulk sync; they are never requested here.
    assert call["include_comments"] is False


def test_named_ids_are_passed_through_to_the_source(client, member):
    """Selecting known work items is not filtering, so it is not a clause — and it
    is the one selection that survived the removal of the legacy filter fields."""
    _, headers = member
    source = FakeSource([[]])
    with ticket_service.use_ticket_source_resolver(resolver_for(source)):
        client.post(
            "/tickets/sync",
            json={"connectionId": 3, "ticketIds": ["SUR-1", "SUR-2"]},
            headers=headers,
        )
    call = source.calls[0]
    assert call["ticket_ids"] == ["SUR-1", "SUR-2"]
    assert call["spec"] is None


def test_a_sync_that_says_nothing_about_what_to_pull_is_refused(client, member):
    """422 rather than read as "everything". A sync that pulls a whole project
    because a field was left out is expensive, surprising, and indistinguishable
    from a caller that meant to send a filter."""
    _, headers = member
    source = FakeSource([[ITEM]])
    with ticket_service.use_ticket_source_resolver(resolver_for(source)):
        response = client.post("/tickets/sync", json={"connectionId": 7}, headers=headers)
    assert response.status_code == 422
    assert "Say what to import" in response.json()["detail"]
    assert source.calls == [], "the provider was called anyway"


def test_a_legacy_selection_field_is_refused_rather_than_ignored(client, member):
    """`mode`/`sprint`/`states`/… are gone (#130). `extra="forbid"` is what makes
    that a 422 instead of a silent whole-project pull — an ignored filter returns
    MORE work items than were asked for."""
    _, headers = member
    for legacy in ("mode", "sprint", "sprintPath", "areaPath"):
        response = client.post(
            "/tickets/sync",
            json={"connectionId": 7, **PULL, legacy: "Sprint 12"},
            headers=headers,
        )
        assert response.status_code == 422, legacy


# ---------------------------------------------------------------- upsert
def test_sync_stores_every_normalised_field(client, member, db_session):
    from app.models.ticket import Ticket

    user, headers = member
    source = FakeSource([[ITEM]])
    with ticket_service.use_ticket_source_resolver(resolver_for(source)):
        body = client.post(
            "/tickets/sync", json={"connectionId": 7, "projectId": 5, **PULL}, headers=headers
        ).json()

    assert body["synced"] == 1
    ticket = db_session.query(Ticket).one()
    assert ticket.external_id == "SUR-1428"
    assert ticket.provider_kind == "ado"
    assert ticket.connection_id == 7  # stamped with its origin
    assert ticket.project_id == 5
    assert ticket.owner_id == user.id  # and with its owner
    assert ticket.work_item_type == "Bug"
    assert ticket.acceptance_criteria == ["Given a file", "Then it imports"]
    assert ticket.acceptance_criteria_html == "<ol><li>Given a file</li></ol>"
    assert ticket.linked_prs == [{"id": 42}]
    # The adapters normalise the work item's own page; the hub used to drop it.
    assert ticket.url == "https://dev.azure.com/emesoft/Surency/_workitems/edit/1428"
    assert not hasattr(ticket, "note")  # the hub stores no QA annotation


def test_resync_updates_in_place_rather_than_duplicating(client, member, db_session):
    from app.models.ticket import Ticket

    _, headers = member
    changed = {**ITEM, "title": "Eligibility import fixed", "status": "Done"}
    source = FakeSource([[ITEM], [changed]])

    with ticket_service.use_ticket_source_resolver(resolver_for(source)):
        first = client.post("/tickets/sync", json={"connectionId": 7, **PULL}, headers=headers).json()
        second = client.post("/tickets/sync", json={"connectionId": 7, **PULL}, headers=headers).json()

    assert first["synced"] == second["synced"] == 1
    assert first["tickets"][0]["id"] == second["tickets"][0]["id"]  # same row
    rows = db_session.query(Ticket).all()
    assert len(rows) == 1
    assert rows[0].title == "Eligibility import fixed"
    assert rows[0].status == "Done"


def test_resync_of_a_partial_payload_clears_rather_than_keeps_stale_values(
    client, member, db_session
):
    """The provider is the source of truth: a field it no longer sends must not
    linger from the previous sync."""
    from app.models.ticket import Ticket

    _, headers = member
    source = FakeSource([[ITEM], [{"external_id": "SUR-1428", "title": "Bare"}]])
    with ticket_service.use_ticket_source_resolver(resolver_for(source)):
        client.post("/tickets/sync", json={"connectionId": 7, **PULL}, headers=headers)
        client.post("/tickets/sync", json={"connectionId": 7, **PULL}, headers=headers)

    ticket = db_session.query(Ticket).one()
    assert ticket.title == "Bare"
    assert ticket.acceptance_criteria == []
    assert ticket.labels == []
    assert ticket.assignee == ""


def test_the_same_external_id_in_two_providers_is_two_rows(client, member, db_session):
    from app.models.ticket import Ticket

    _, headers = member
    item = {"external_id": "1428", "title": "shared id"}
    with ticket_service.use_ticket_source_resolver(
        resolver_for(FakeSource([[item]]), provider_kind="ado")
    ):
        client.post("/tickets/sync", json={"providerKind": "ado", **PULL}, headers=headers)
    with ticket_service.use_ticket_source_resolver(
        resolver_for(FakeSource([[item]]), provider_kind="jira")
    ):
        client.post("/tickets/sync", json={"providerKind": "jira", **PULL}, headers=headers)

    assert db_session.query(Ticket).count() == 2


def test_an_item_without_an_external_id_is_skipped(client, member, db_session):
    from app.models.ticket import Ticket

    _, headers = member
    source = FakeSource([[{"title": "nameless"}, ITEM]])
    with ticket_service.use_ticket_source_resolver(resolver_for(source)):
        body = client.post("/tickets/sync", json={"connectionId": 7, **PULL}, headers=headers).json()

    assert body["synced"] == 1
    assert db_session.query(Ticket).count() == 1


# ---------------------------------------------------------------- isolation
def test_a_resync_never_touches_another_members_identical_ticket(
    client, make_user, auth_headers, db_session
):
    from app.models.ticket import Ticket

    alice = make_user("alice-s@emesoft.net", "password12345")
    bob = make_user("bob-s@emesoft.net", "password12345")
    db_session.add(
        Ticket(external_id="SUR-1428", provider_kind="ado", title="Alice's", owner_id=alice.id)
    )
    db_session.commit()

    source = FakeSource([[ITEM]])
    with ticket_service.use_ticket_source_resolver(resolver_for(source)):
        client.post(
            "/tickets/sync",
            json={"connectionId": 7, **PULL},
            headers=auth_headers("bob-s@emesoft.net", "password12345"),
        )

    rows = {t.owner_id: t.title for t in db_session.query(Ticket).all()}
    assert rows[alice.id] == "Alice's"  # untouched
    assert rows[bob.id] == "Eligibility import fails"


def test_a_sync_updates_a_shared_ticket_rather_than_shadowing_it(client, member, db_session):
    """``owner_id IS NULL`` is the shared namespace and is visible to the member,
    so a re-sync of the same work item updates it instead of forking a copy."""
    from app.models.ticket import Ticket

    _, headers = member
    db_session.add(Ticket(external_id="SUR-1428", provider_kind="ado", title="Shared"))
    db_session.commit()

    with ticket_service.use_ticket_source_resolver(resolver_for(FakeSource([[ITEM]]))):
        client.post("/tickets/sync", json={"connectionId": 7, **PULL}, headers=headers)

    ticket = db_session.query(Ticket).one()
    assert ticket.owner_id is None
    assert ticket.title == "Eligibility import fails"


# ---------------------------------------------------------------- failures
def test_a_provider_failure_is_a_502(client, member):
    _, headers = member

    class Exploding:
        def fetch_tickets(self, **_):
            raise RuntimeError("ADO returned 500")

    with ticket_service.use_ticket_source_resolver(resolver_for(Exploding())):
        response = client.post("/tickets/sync", json={"connectionId": 7, **PULL}, headers=headers)
    assert response.status_code == 502
    assert "ADO returned 500" in response.json()["detail"]


def test_no_such_connection_is_a_404(client, member):
    _, headers = member

    def _missing(db, user, connection_id, provider_kind):
        raise LookupError("No work-item connection is configured for 'jira'")

    with ticket_service.use_ticket_source_resolver(_missing):
        response = client.post("/tickets/sync", json={"providerKind": "jira", **PULL}, headers=headers)
    assert response.status_code == 404


# ---------------------------------------------------------------- after-effects
def test_synced_tickets_are_immediately_readable(client, member):
    _, headers = member
    with ticket_service.use_ticket_source_resolver(resolver_for(FakeSource([[ITEM]]))):
        client.post("/tickets/sync", json={"connectionId": 7, **PULL}, headers=headers)

    listed = client.get("/tickets?providerKind=ado", headers=headers).json()
    assert [t["externalId"] for t in listed["items"]] == ["SUR-1428"]
    detail = client.get("/tickets/SUR-1428", headers=headers).json()
    assert detail["acceptanceCriteria"] == ["Given a file", "Then it imports"]


def test_sync_is_audited_as_a_ticket_event(client, member, db_session):
    from app.models.audit import AuditLog

    user, headers = member
    with ticket_service.use_ticket_source_resolver(resolver_for(FakeSource([[ITEM]]))):
        client.post(
            "/tickets/sync", json={"connectionId": 7, **PULL}, headers=headers
        )

    event = db_session.query(AuditLog).filter(AuditLog.category == "ticket").one()
    assert event.action == "Synced tickets"
    # The connection's label, not a sprint name: the selection is no longer one
    # field, so the audit row names the source and describes the ask separately.
    assert event.target == "ADO — Surency"
    assert event.meta == "1 work items · 1 named"
    assert event.actor_id == user.id
    assert event.owner_id == user.id
