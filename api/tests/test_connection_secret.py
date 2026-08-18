"""``GET /connections/{id}/secret`` — the one endpoint that returns a PAT.

ADR 0010. The negative cases below **are** the design: this route is the single
deliberate hole in "the PAT never leaves the hub", so what it refuses matters more
than what it returns. Each test here corresponds to one of the five properties
the ADR claims keep it narrow.

The sibling assertion — that every *other* endpoint of the router still leaks
nothing — stays in :mod:`test_connections`.
"""

from __future__ import annotations

import pytest

from app.config import AUDIENCE_DAGENT, AUDIENCE_QAGENT
from app.models.audit import AuditLog
from app.models.provider_connection import ProviderConnection

PAT = "ghp-super-secret-pat-value-0123456789"
PASSWORD = "password12345"


@pytest.fixture
def member(make_user):
    return make_user("member@emesoft.net", PASSWORD, role="member")


@pytest.fixture
def other(make_user):
    return make_user("other@emesoft.net", PASSWORD, role="member")


def _hub_headers(auth_headers, email: str = "member@emesoft.net"):
    return auth_headers(email, PASSWORD)


def _agent_headers(login, audience: str, email: str = "member@emesoft.net"):
    token = login(email, PASSWORD)["tokens"][audience]
    return {"Authorization": f"Bearer {token}"}


def _create(client, headers, **overrides):
    body = {
        "kind": "azure_devops",
        "label": "EMESOFT — Surveyor",
        "baseUrl": "https://dev.azure.com/emesoft",
        "config": {"project": "Surveyor"},
        "pat": PAT,
        **overrides,
    }
    response = client.post("/connections", json=body, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()


# ------------------------------------------------------------ the whole point
def test_an_agent_reads_the_credential_it_needs(client, member, auth_headers, login):
    """The case the endpoint exists for: DAgent gets what it must put in an MCP
    config — the PAT, plus the org URL and project that go beside it."""
    created = _create(client, _hub_headers(auth_headers))

    response = client.get(
        f"/connections/{created['id']}/secret",
        headers=_agent_headers(login, AUDIENCE_DAGENT),
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["pat"] == PAT
    assert body["baseUrl"] == "https://dev.azure.com/emesoft"
    assert body["config"] == {"project": "Surveyor"}
    assert body["kind"] == "azure_devops"
    # The agent's cache key — without it there is no way to notice a rotation.
    assert body["updatedAt"]


def test_any_registered_agent_audience_passes(client, member, auth_headers, login):
    """Not DAgent-only. The blocker is structural rather than product-specific,
    and QAgent has the same one for cloning a repository."""
    created = _create(client, _hub_headers(auth_headers))
    response = client.get(
        f"/connections/{created['id']}/secret",
        headers=_agent_headers(login, AUDIENCE_QAGENT),
    )
    assert response.status_code == 200, response.text
    assert response.json()["pat"] == PAT


# ------------------------------------------------------------------- refusals
def test_the_hubs_own_audience_is_refused(client, member, auth_headers):
    """Property 1. The hub's SPA deliberately never shows a PAT, so a browser
    origin holding a hub token must not be able to read one either."""
    hdrs = _hub_headers(auth_headers)
    created = _create(client, hdrs)

    response = client.get(f"/connections/{created['id']}/secret", headers=hdrs)

    assert response.status_code == 400
    assert PAT not in response.text


def test_an_unauthenticated_caller_is_refused(client, member, auth_headers):
    created = _create(client, _hub_headers(auth_headers))
    response = client.get(f"/connections/{created['id']}/secret")
    assert response.status_code == 401
    assert PAT not in response.text


def test_another_members_connection_404s(client, member, other, auth_headers, login):
    """Property 3. A 403 would confirm the row exists, which is itself a
    disclosure — the same rule every other connection read follows."""
    created = _create(client, _hub_headers(auth_headers))

    response = client.get(
        f"/connections/{created['id']}/secret",
        headers=_agent_headers(login, AUDIENCE_DAGENT, "other@emesoft.net"),
    )

    assert response.status_code == 404
    assert PAT not in response.text


def test_a_connection_with_no_stored_credential_404s(
    client, member, auth_headers, login
):
    created = _create(client, _hub_headers(auth_headers), pat=None)
    response = client.get(
        f"/connections/{created['id']}/secret",
        headers=_agent_headers(login, AUDIENCE_DAGENT),
    )
    assert response.status_code == 404


def test_an_undecryptable_credential_is_a_502_not_an_empty_pat(
    client, member, auth_headers, login, db_session
):
    """Property 5. Passing an unusable credential on as ``""`` would make the
    agent fail against the provider instead of here, where the cause is known."""
    created = _create(client, _hub_headers(auth_headers))
    row = db_session.get(ProviderConnection, created["id"])
    row.pat_encrypted = "enc::v1:this-is-not-a-valid-fernet-token"
    db_session.commit()

    response = client.get(
        f"/connections/{created['id']}/secret",
        headers=_agent_headers(login, AUDIENCE_DAGENT),
    )

    assert response.status_code == 502
    assert "decrypt" in response.json()["detail"].lower()


# --------------------------------------------------------------------- audit
def test_every_call_is_audited_with_the_calling_agent(
    client, member, auth_headers, login, db_session
):
    """Property 4. The credential leaves the hub; the audit row is the only
    record that it did, so it carries *which* agent asked."""
    created = _create(client, _hub_headers(auth_headers))
    client.get(
        f"/connections/{created['id']}/secret",
        headers=_agent_headers(login, AUDIENCE_DAGENT),
    )

    rows = (
        db_session.query(AuditLog)
        .filter(AuditLog.target == f"connection:{created['id']}:azure_devops")
        .all()
    )
    assert len(rows) == 1
    assert rows[0].source == AUDIENCE_DAGENT
    assert rows[0].status == "success"
    assert PAT not in str(rows[0].__dict__)


def test_a_miss_is_audited_too(client, member, auth_headers, login, db_session):
    """A resolve that found nothing is as interesting as one that succeeded —
    it is what an agent misconfigured against the wrong connection looks like."""
    created = _create(client, _hub_headers(auth_headers), pat=None)
    client.get(
        f"/connections/{created['id']}/secret",
        headers=_agent_headers(login, AUDIENCE_DAGENT),
    )

    rows = (
        db_session.query(AuditLog)
        .filter(AuditLog.target == f"connection:{created['id']}:azure_devops")
        .all()
    )
    assert len(rows) == 1
    assert rows[0].status == "warning"


# ------------------------------------------------------- change detection
def test_updated_at_moves_when_the_pat_is_rotated(client, member, auth_headers, login):
    """The mechanism the agent's re-sync rests on. If a rotation did not bump
    ``updatedAt``, a mirrored PAT would go stale silently — which is the drift
    the hub exists to remove, wearing a new hat."""
    hdrs = _hub_headers(auth_headers)
    created = _create(client, hdrs)
    before = client.get("/connections", headers=hdrs).json()[0]["updatedAt"]

    client.patch(f"/connections/{created['id']}", json={"pat": "rotated-pat"}, headers=hdrs)

    after = client.get("/connections", headers=hdrs).json()[0]["updatedAt"]
    assert after != before

    secret = client.get(
        f"/connections/{created['id']}/secret",
        headers=_agent_headers(login, AUDIENCE_DAGENT),
    ).json()
    assert secret["pat"] == "rotated-pat"
    assert secret["updatedAt"] == after
