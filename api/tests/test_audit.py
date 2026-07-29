"""The audit trail, and ``POST /audit/events`` from an agent."""

from __future__ import annotations

from app.config import AUDIENCE_DAGENT, AUDIENCE_HUB, AUDIENCE_QAGENT


def test_login_is_audited(client, make_user, auth_headers):
    make_user("audited@emesoft.net", "password12345")
    headers = auth_headers("audited@emesoft.net", "password12345")

    events = client.get("/audit/events", headers=headers).json()
    signed_in = [e for e in events if e["action"] == "Signed in"]
    assert signed_in
    assert signed_in[0]["category"] == "auth"
    assert signed_in[0]["source"] == AUDIENCE_HUB
    assert signed_in[0]["target"] == "audited@emesoft.net"


def test_an_agent_appends_an_event_attributed_to_itself(client, make_user, login):
    make_user("agentuser@emesoft.net", "password12345")
    tokens = login("agentuser@emesoft.net", "password12345")["tokens"]
    agent_headers = {"Authorization": f"Bearer {tokens[AUDIENCE_QAGENT]}"}

    response = client.post(
        "/audit/events",
        json={
            "category": "agent",
            "action": "Executed run RUN-204",
            "actorType": "agent",
            "target": "RUN-204",
            "meta": "12 cases",
        },
        headers=agent_headers,
    )
    assert response.status_code == 201, response.text

    hub_headers = {"Authorization": f"Bearer {tokens[AUDIENCE_HUB]}"}
    events = client.get("/audit/events?source=qagent", headers=hub_headers).json()
    assert len(events) == 1
    assert events[0]["source"] == AUDIENCE_QAGENT
    assert events[0]["action"] == "Executed run RUN-204"
    assert events[0]["actor"] == "agentuser@emesoft.net"


def test_the_source_comes_from_the_token_not_the_body(client, make_user, login):
    """A DAgent token cannot append an event claiming to be the hub."""
    make_user("spoof@emesoft.net", "password12345")
    tokens = login("spoof@emesoft.net", "password12345")["tokens"]

    client.post(
        "/audit/events",
        json={"category": "agent", "action": "sneaky", "source": "emehub"},
        headers={"Authorization": f"Bearer {tokens[AUDIENCE_DAGENT]}"},
    )
    events = client.get(
        "/audit/events?category=agent",
        headers={"Authorization": f"Bearer {tokens[AUDIENCE_HUB]}"},
    ).json()
    assert [e["source"] for e in events] == [AUDIENCE_DAGENT]


def test_appending_requires_authentication(client):
    assert client.post("/audit/events", json={"action": "anon"}).status_code == 401


def test_bad_category_or_status_is_rejected(client, make_user, auth_headers):
    make_user("validate@emesoft.net", "password12345")
    headers = auth_headers("validate@emesoft.net", "password12345")

    assert (
        client.post(
            "/audit/events", json={"category": "nonsense", "action": "x"}, headers=headers
        ).status_code
        == 400
    )
    assert (
        client.post(
            "/audit/events",
            json={"category": "agent", "action": "x", "status": "maybe"},
            headers=headers,
        ).status_code
        == 400
    )
    assert (
        client.post(
            "/audit/events", json={"category": "agent", "action": "  "}, headers=headers
        ).status_code
        == 400
    )


def test_record_never_raises(db_session, monkeypatch):
    """Auditing must never break the action being audited."""
    from app.services import audit_service

    class Boom:
        def __getattr__(self, name):
            raise RuntimeError("database on fire")

    monkeypatch.setattr(audit_service.db_module, "SessionLocal", lambda: Boom())
    audit_service.record(category="auth", action="still fine")  # must not raise
