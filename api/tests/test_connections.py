"""Provider connection endpoints — and the promise the slice exists to keep.

The load-bearing test here is
:func:`test_the_pat_never_appears_in_any_connection_response`, which walks every
endpoint the router exposes and asserts the stored secret is in none of their
bodies (CLAUDE.md › "Provider PATs never leave the hub"; INTEGRATION.md §4).

**One endpoint is excluded, deliberately and by name**: ``GET /connections/{id}/secret``
returns the PAT to an agent audience (ADR 0010). It is covered by
:mod:`test_connection_secret`, where the refusals are the point. Excluding it by
hand rather than by introspection is intentional — a future route must not be
able to escape this assertion by being forgotten.

The rest cover encryption at rest, per-owner isolation, the shared namespace and
the capability rules.
"""

from __future__ import annotations

import pytest

from app import crypto
from app.config import AUDIENCE_QAGENT
from app.models.provider_connection import ProviderConnection

#: Distinctive enough that finding it in a response body is unambiguous.
PAT = "ghp-super-secret-pat-value-0123456789"
PASSWORD = "password12345"


@pytest.fixture
def member(make_user):
    return make_user("member@emesoft.net", PASSWORD, role="member")


@pytest.fixture
def other(make_user):
    return make_user("other@emesoft.net", PASSWORD, role="member")


@pytest.fixture
def admin(make_user):
    return make_user("admin@emesoft.net", PASSWORD, role="admin")


@pytest.fixture
def headers(auth_headers):
    def _for(email: str):
        return auth_headers(email, PASSWORD)

    return _for


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
def test_the_pat_never_appears_in_any_connection_response(client, member, headers):
    """Walk every endpoint of the router; the PAT is in none of the bodies.

    Endpoints that reach the provider are included: their failure paths echo
    upstream messages and exception strings, which is exactly where a credential
    would slip out. The connection points at an unroutable host so those calls
    fail — which is the interesting case, not an inconvenience.

    ``GET /{id}/secret`` is the one exclusion and is listed in the module
    docstring; see :mod:`test_connection_secret`.
    """
    hdrs = headers("member@emesoft.net")
    created = _create(
        client,
        hdrs,
        baseUrl="https://dev.azure.invalid/emesoft",
        capabilities=["work_item", "repository"],
    )
    cid = created["id"]

    responses = [
        ("POST /connections", created),
        ("GET /connections", client.get("/connections", headers=hdrs).json()),
        (
            "PATCH /connections/{id}",
            client.patch(f"/connections/{cid}", json={"label": "Renamed"}, headers=hdrs).json(),
        ),
        (
            "POST /connections/{id}/test",
            client.post(f"/connections/{cid}/test", headers=hdrs).json(),
        ),
        (
            "GET /connections/{id}/sprints",
            client.get(f"/connections/{cid}/sprints", headers=hdrs).json(),
        ),
        (
            "GET /connections/{id}/projects",
            client.get(f"/connections/{cid}/projects", headers=hdrs).json(),
        ),
        (
            "GET /connections/{id}/work-item-metadata",
            client.get(f"/connections/{cid}/work-item-metadata", headers=hdrs).json(),
        ),
        (
            "GET /connections/{id}/repos",
            client.get(f"/connections/{cid}/repos", headers=hdrs).json(),
        ),
    ]
    for name, body in responses:
        assert PAT not in str(body), f"{name} leaked the PAT"
        # Not even a fragment of it, and not the field by any name.
        assert PAT[:12] not in str(body), f"{name} leaked part of the PAT"
        assert "pat" not in _keys(body) - {"hasPat"}, f"{name} exposes a pat field"

    # The delete response has no body at all, but check the status is real.
    assert client.delete(f"/connections/{cid}", headers=hdrs).status_code == 204


def test_nothing_logs_the_pat_even_when_the_provider_is_unreachable(
    client, member, headers, caplog
):
    """Not truncated, not at debug level. The adapter error paths are the risk:
    an exception string can carry a URL, and a log line is where a credential
    ends up unnoticed."""
    import logging

    hdrs = headers("member@emesoft.net")
    with caplog.at_level(logging.DEBUG):
        created = _create(client, hdrs, baseUrl="https://dev.azure.invalid/emesoft")
        cid = created["id"]
        client.post(f"/connections/{cid}/test", headers=hdrs)
        client.get(f"/connections/{cid}/sprints", headers=hdrs)
        client.get(f"/connections/{cid}/projects", headers=hdrs)
        client.get(f"/connections/{cid}/work-item-metadata", headers=hdrs)
        client.get(f"/connections/{cid}/repos", headers=hdrs)

    assert PAT not in caplog.text
    assert PAT[:8] not in caplog.text


def _keys(body) -> set[str]:
    """Every key appearing anywhere in a nested response body."""
    if isinstance(body, dict):
        found = set(body)
        for value in body.values():
            found |= _keys(value)
        return found
    if isinstance(body, list):
        found: set[str] = set()
        for item in body:
            found |= _keys(item)
        return found
    return set()


def test_the_response_says_has_pat_and_nothing_more(client, member, headers):
    created = _create(client, headers("member@emesoft.net"))
    assert created["hasPat"] is True
    assert "pat" not in created
    assert "patEncrypted" not in created

    without = _create(client, headers("member@emesoft.net"), pat=None, label="No credential")
    assert without["hasPat"] is False


def test_the_pat_is_encrypted_at_rest_and_round_trips(client, db_session, member, headers):
    """The stored column is an ``enc::v1:`` envelope, not the plaintext."""
    created = _create(client, headers("member@emesoft.net"))
    row = db_session.get(ProviderConnection, created["id"])

    assert row.pat_encrypted != PAT
    assert row.pat_encrypted.startswith("enc::v1:")
    assert crypto.is_encrypted(row.pat_encrypted)
    assert crypto.decrypt(row.pat_encrypted) == PAT


def test_config_may_not_carry_a_credential(client, member, headers):
    """``config`` is echoed back verbatim, so a secret parked there would be a
    secret in a response body. Refused at the door."""
    hdrs = headers("member@emesoft.net")
    for key in ("pat", "apiToken", "password", "api_key", "clientSecret"):
        response = client.post(
            "/connections",
            json={"kind": "github", "config": {key: "leak-me"}},
            headers=hdrs,
        )
        assert response.status_code == 400, f"{key} was accepted into config"
        assert "secret" in response.json()["detail"].lower()

    created = _create(client, hdrs)
    patched = client.patch(
        f"/connections/{created['id']}", json={"config": {"authToken": "x"}}, headers=hdrs
    )
    assert patched.status_code == 400


# ---------------------------------------------------------------- capabilities
def test_a_connection_defaults_to_its_kinds_capabilities(client, member, headers):
    hdrs = headers("member@emesoft.net")
    ado = _create(client, hdrs, kind="azure_devops")
    github = _create(client, hdrs, kind="github", config={})
    jira = _create(client, hdrs, kind="jira", config={"project": "SUR"})

    assert ado["capabilities"] == ["work_item", "repository"]
    assert github["capabilities"] == ["work_item", "repository"]
    assert jira["capabilities"] == ["work_item"]
    assert jira["supportedCapabilities"] == ["work_item"]


def test_a_connection_may_narrow_but_not_widen_its_capabilities(client, member, headers):
    hdrs = headers("member@emesoft.net")
    narrowed = _create(client, hdrs, kind="github", config={}, capabilities=["repository"])
    assert narrowed["capabilities"] == ["repository"]

    # Jira hosts no git; asking for it is a 400, not a silently ignored field.
    refused = client.post(
        "/connections",
        json={"kind": "jira", "capabilities": ["repository"]},
        headers=hdrs,
    )
    assert refused.status_code == 400
    assert "repository" in refused.json()["detail"]

    empty = client.post(
        "/connections", json={"kind": "github", "capabilities": []}, headers=hdrs
    )
    assert empty.status_code == 400


def test_a_metadata_read_refuses_a_capability_the_connection_lacks(client, member, headers):
    hdrs = headers("member@emesoft.net")
    repo_only = _create(client, hdrs, kind="github", config={}, capabilities=["repository"])
    response = client.get(f"/connections/{repo_only['id']}/sprints", headers=hdrs)
    assert response.status_code == 400
    assert "work_item" in response.json()["detail"]


def test_an_unknown_kind_is_refused(client, member, headers):
    response = client.post(
        "/connections", json={"kind": "gitlab"}, headers=headers("member@emesoft.net")
    )
    assert response.status_code == 400


# ------------------------------------------------------------------ isolation
def test_a_member_never_sees_another_members_connection(client, member, other, headers):
    mine = _create(client, headers("member@emesoft.net"), label="Mine")
    theirs = _create(client, headers("other@emesoft.net"), label="Theirs")

    visible = client.get("/connections", headers=headers("member@emesoft.net")).json()
    assert [c["label"] for c in visible] == ["Mine"]
    assert theirs["id"] not in [c["id"] for c in visible]

    # And cannot reach it by id — 404, not 403: a 403 confirms it exists.
    hdrs = headers("member@emesoft.net")
    assert client.get(f"/connections/{theirs['id']}/repos", headers=hdrs).status_code == 404
    assert client.patch(
        f"/connections/{theirs['id']}", json={"label": "hijacked"}, headers=hdrs
    ).status_code == 404
    assert client.delete(f"/connections/{theirs['id']}", headers=hdrs).status_code == 404
    assert client.post(f"/connections/{theirs['id']}/test", headers=hdrs).status_code == 404
    _ = mine


def test_a_shared_connection_is_visible_to_everyone(client, admin, member, headers):
    shared = _create(client, headers("admin@emesoft.net"), label="Workspace ADO", shared=True)
    assert shared["shared"] is True

    seen = client.get("/connections", headers=headers("member@emesoft.net")).json()
    assert [c["label"] for c in seen] == ["Workspace ADO"]
    # Visible, still without the credential.
    assert seen[0]["hasPat"] is True
    assert PAT not in str(seen)


def test_only_an_admin_may_create_or_modify_a_shared_connection(
    client, admin, member, headers
):
    member_hdrs = headers("member@emesoft.net")
    refused = client.post(
        "/connections", json={"kind": "github", "shared": True}, headers=member_hdrs
    )
    assert refused.status_code == 403

    shared = _create(client, headers("admin@emesoft.net"), shared=True)
    # A member can see it but not change what everyone else authenticates as.
    assert client.patch(
        f"/connections/{shared['id']}", json={"label": "mine now"}, headers=member_hdrs
    ).status_code == 403
    assert client.delete(f"/connections/{shared['id']}", headers=member_hdrs).status_code == 403


# ----------------------------------------------------------------- update rules
def test_an_omitted_pat_is_kept_and_an_empty_one_clears_it(
    client, db_session, member, headers
):
    hdrs = headers("member@emesoft.net")
    created = _create(client, hdrs)
    cid = created["id"]

    kept = client.patch(f"/connections/{cid}", json={"label": "Renamed"}, headers=hdrs).json()
    assert kept["label"] == "Renamed"
    assert kept["hasPat"] is True
    assert crypto.decrypt(db_session.get(ProviderConnection, cid).pat_encrypted) == PAT

    replaced = client.patch(f"/connections/{cid}", json={"pat": "new-token"}, headers=hdrs).json()
    assert replaced["hasPat"] is True
    db_session.expire_all()
    assert crypto.decrypt(db_session.get(ProviderConnection, cid).pat_encrypted) == "new-token"

    cleared = client.patch(f"/connections/{cid}", json={"pat": ""}, headers=hdrs).json()
    assert cleared["hasPat"] is False
    db_session.expire_all()
    assert db_session.get(ProviderConnection, cid).pat_encrypted is None


def test_replacing_the_pat_marks_the_connection_unproven(client, db_session, member, headers):
    hdrs = headers("member@emesoft.net")
    created = _create(client, hdrs)
    row = db_session.get(ProviderConnection, created["id"])
    row.connected = True
    db_session.commit()

    patched = client.patch(
        f"/connections/{created['id']}", json={"pat": "rotated"}, headers=hdrs
    ).json()
    assert patched["connected"] is False


def test_the_audit_trail_records_the_change_but_never_the_value(
    client, db_session, member, headers
):
    hdrs = headers("member@emesoft.net")
    created = _create(client, hdrs)
    client.patch(f"/connections/{created['id']}", json={"pat": PAT}, headers=hdrs)

    from app.models.audit import AuditLog

    events = db_session.query(AuditLog).filter(AuditLog.category == "connection").all()
    assert {e.action for e in events} >= {
        "Added provider connection",
        "Updated provider connection",
    }
    for event in events:
        assert PAT not in f"{event.action}{event.target}{event.meta}{event.detail}"
    # The update records *which* fields moved, by name.
    updated = next(e for e in events if e.action == "Updated provider connection")
    assert updated.meta == "pat"


# ---------------------------------------------------------------- auth posture
def test_every_connection_endpoint_refuses_an_anonymous_caller(client, member):
    cases = [
        ("get", "/connections"),
        ("post", "/connections"),
        ("patch", "/connections/1"),
        ("delete", "/connections/1"),
        ("post", "/connections/1/test"),
        ("get", "/connections/1/sprints"),
        ("get", "/connections/1/projects"),
        ("get", "/connections/1/work-item-metadata"),
        ("get", "/connections/1/repos"),
    ]
    for method, path in cases:
        assert getattr(client, method)(path).status_code == 401, f"{method} {path}"


def test_an_agent_token_reads_the_catalogue_and_can_do_nothing_else(
    client, member, login, headers
):
    """INTEGRATION.md §3 puts ``GET /connections`` in the contract, so an agent's
    own token must reach it. Managing a connection is the hub's own business."""
    _create(client, headers("member@emesoft.net"), label="Visible to agents")
    agent = login("member@emesoft.net", PASSWORD)["tokens"][AUDIENCE_QAGENT]
    agent_headers = {"Authorization": f"Bearer {agent}"}

    listed = client.get("/connections", headers=agent_headers)
    assert listed.status_code == 200
    assert [c["label"] for c in listed.json()] == ["Visible to agents"]
    assert PAT not in listed.text

    assert client.post(
        "/connections", json={"kind": "github"}, headers=agent_headers
    ).status_code == 401
    assert client.post("/connections/1/test", headers=agent_headers).status_code == 401
    assert client.get("/connections/1/repos", headers=agent_headers).status_code == 401


def test_the_proxy_endpoint_is_not_implemented(client, member, headers):
    """INTEGRATION.md §4 defers ``POST /connections/{id}/proxy``. It is absent
    rather than half-built — this test fails the day someone stubs it."""
    hdrs = headers("member@emesoft.net")
    created = _create(client, hdrs)
    response = client.post(f"/connections/{created['id']}/proxy", json={}, headers=hdrs)
    assert response.status_code == 404
