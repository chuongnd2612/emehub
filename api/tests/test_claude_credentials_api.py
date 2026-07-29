"""Claude credentials over HTTP — posture, isolation, and the audited leak.

The security properties this slice exists to guarantee:

* only ``GET /credentials/claude/resolve`` ever returns credential material;
* every call to it is audited (INTEGRATION.md §4);
* a member can never read another member's credential;
* only an admin may write or delete the shared credential;
* an agent token may resolve, but may not manage.
"""

from __future__ import annotations

import json

import pytest

from app.config import AUDIENCE_QAGENT
from tests.test_claude_credentials import OTHER_TOKEN, TOKEN, creds_file

PASSWORD = "password12345"


@pytest.fixture
def actors(make_user):
    make_user("member-a@emesoft.net", PASSWORD)
    make_user("member-b@emesoft.net", PASSWORD)
    make_user("boss@emesoft.net", PASSWORD, role="admin")


@pytest.fixture
def hub(auth_headers, actors):
    """``Authorization`` headers carrying hub-audience tokens."""
    return {
        "a": auth_headers("member-a@emesoft.net", PASSWORD),
        "b": auth_headers("member-b@emesoft.net", PASSWORD),
        "admin": auth_headers("boss@emesoft.net", PASSWORD),
    }


@pytest.fixture
def agent_headers(login, actors):
    """A ``qagent``-audience token — what an agent actually calls with."""

    def _headers(email: str = "member-a@emesoft.net"):
        token = login(email, PASSWORD)["tokens"][AUDIENCE_QAGENT]
        return {"Authorization": f"Bearer {token}"}

    return _headers


def upload_own(client, headers, raw=None, label="laptop"):
    return client.put(
        "/credentials/claude",
        json={"credentials": raw or creds_file(TOKEN), "label": label},
        headers=headers,
    )


def upload_shared(client, headers, raw=None, label="workspace"):
    return client.put(
        "/credentials/claude/shared",
        json={"credentials": raw or creds_file(OTHER_TOKEN), "label": label},
        headers=headers,
    )


# ------------------------------------------------------------- happy paths
def test_upload_then_status_reports_metadata_only(client, hub):
    body = upload_own(client, hub["a"]).json()
    assert body["hasOwn"] is True
    assert body["mode"] == "own"
    assert body["own"]["label"] == "laptop"
    assert body["own"]["subscriptionType"] == "max"
    assert body["own"]["scopes"] == ["user:inference"]
    assert body["own"]["daysLeft"] >= 29

    status = client.get("/credentials/claude", headers=hub["a"])
    assert status.status_code == 200
    assert TOKEN not in status.text


def test_an_invalid_file_is_rejected_with_the_canonical_message(client, hub):
    response = client.put(
        "/credentials/claude",
        json={"credentials": '{"nope": true}'},
        headers=hub["a"],
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "Expected a claudeAiOauth token object"
    assert client.get("/credentials/claude", headers=hub["a"]).json()["hasOwn"] is False


def test_delete_own_falls_back_to_the_shared_credential(client, hub):
    upload_shared(client, hub["admin"])
    upload_own(client, hub["a"])
    assert client.delete("/credentials/claude", headers=hub["a"]).status_code == 200

    status = client.get("/credentials/claude", headers=hub["a"]).json()
    assert status["hasOwn"] is False
    assert status["mode"] == "shared"


def test_mode_switches_without_deleting_the_upload(client, hub):
    upload_shared(client, hub["admin"])
    upload_own(client, hub["a"])

    body = client.put(
        "/credentials/claude/mode", json={"mode": "shared"}, headers=hub["a"]
    ).json()
    assert body["mode"] == "shared"
    assert body["hasOwn"] is True  # still on file

    body = client.put(
        "/credentials/claude/mode", json={"mode": "own"}, headers=hub["a"]
    ).json()
    assert body["mode"] == "own"


def test_mode_rejects_shared_when_none_is_configured(client, hub):
    upload_own(client, hub["a"])
    response = client.put(
        "/credentials/claude/mode", json={"mode": "shared"}, headers=hub["a"]
    )
    assert response.status_code == 400


def test_test_endpoint_reports_storage_health_without_the_token(client, hub):
    assert client.post("/credentials/claude/test", headers=hub["a"]).json()["result"] == (
        "no_credential"
    )
    upload_own(client, hub["a"])
    response = client.post("/credentials/claude/test", headers=hub["a"])
    assert response.json() == {
        "ok": True,
        "result": "ok",
        "message": "Credential is stored and readable.",
    }
    assert TOKEN not in response.text


def test_test_endpoint_can_target_the_shared_account(client, hub):
    upload_shared(client, hub["admin"], creds_file(OTHER_TOKEN, days=-4))
    upload_own(client, hub["admin"], creds_file(TOKEN, days=30))
    results = {
        scope: client.post(
            f"/credentials/claude/test?scope={scope}", headers=hub["admin"]
        ).json()["result"]
        for scope in ("own", "shared", "effective")
    }
    assert results == {"own": "ok", "shared": "expired", "effective": "ok"}


# ------------------------------------------------------------ shared is admin-only
def test_a_member_cannot_write_the_shared_credential(client, hub):
    assert upload_shared(client, hub["b"]).status_code == 403
    assert client.get("/credentials/claude", headers=hub["b"]).json()["hasShared"] is False


def test_a_member_cannot_delete_the_shared_credential(client, hub):
    upload_shared(client, hub["admin"])
    assert client.delete("/credentials/claude/shared", headers=hub["b"]).status_code == 403
    assert client.get("/credentials/claude", headers=hub["b"]).json()["hasShared"] is True

    assert client.delete("/credentials/claude/shared", headers=hub["admin"]).status_code == 200
    assert client.get("/credentials/claude", headers=hub["b"]).json()["hasShared"] is False


# ----------------------------------------------------------- cross-user isolation
def test_a_member_cannot_read_another_members_credential(client, hub):
    upload_own(client, hub["a"])

    status = client.get("/credentials/claude", headers=hub["b"])
    assert status.json()["hasOwn"] is False
    assert TOKEN not in status.text

    # With no shared credential to fall back on, B resolves to nothing at all —
    # A's credential is not merely hidden, it is unreachable.
    resolved = client.get("/credentials/claude/resolve", headers=hub["b"])
    assert resolved.status_code == 404
    assert TOKEN not in resolved.text

    assert client.post("/credentials/claude/test", headers=hub["b"]).json()["result"] == (
        "no_credential"
    )


def test_only_the_shared_namespace_is_cross_visible(client, hub):
    upload_own(client, hub["a"], creds_file(TOKEN))
    upload_shared(client, hub["admin"], creds_file(OTHER_TOKEN))

    resolved = client.get("/credentials/claude/resolve", headers=hub["b"]).json()
    assert resolved["source"] == "shared"
    assert OTHER_TOKEN in resolved["credentials"]
    assert TOKEN not in json.dumps(resolved)


def test_deleting_your_own_credential_cannot_touch_anyone_elses(client, hub):
    upload_own(client, hub["a"], creds_file(TOKEN))
    upload_own(client, hub["b"], creds_file(OTHER_TOKEN))
    client.delete("/credentials/claude", headers=hub["b"])

    assert TOKEN in client.get("/credentials/claude/resolve", headers=hub["a"]).json()[
        "credentials"
    ]


# ------------------------------------------------------------------ resolve
def test_resolve_returns_the_credential_and_its_metadata(client, hub):
    raw = creds_file(TOKEN)
    upload_own(client, hub["a"], raw)

    body = client.get("/credentials/claude/resolve", headers=hub["a"]).json()
    assert body["source"] == "own"
    assert body["credentials"] == raw
    assert body["subscriptionType"] == "max"
    assert body["status"] == "active"


def test_resolve_accepts_a_registered_agent_audience(client, hub, agent_headers):
    """INTEGRATION.md §3 — the agent calls this with its own token."""
    upload_own(client, hub["a"])
    response = client.get("/credentials/claude/resolve", headers=agent_headers())
    assert response.status_code == 200
    assert TOKEN in response.json()["credentials"]


def test_resolve_is_refused_without_a_token(client, hub):
    upload_own(client, hub["a"])
    assert client.get("/credentials/claude/resolve").status_code == 401


def test_resolve_404s_when_nothing_is_configured(client, hub):
    assert client.get("/credentials/claude/resolve", headers=hub["a"]).status_code == 404


def _credential_events(client, headers):
    return [
        event
        for event in client.get("/audit/events?category=credential", headers=headers).json()
    ]


def test_every_resolve_is_audited(client, hub, agent_headers):
    """INTEGRATION.md §4 requires it, because the credential leaves the hub."""
    upload_own(client, hub["a"])
    client.get("/credentials/claude/resolve", headers=hub["a"])
    client.get("/credentials/claude/resolve", headers=agent_headers())

    events = _credential_events(client, hub["a"])
    resolves = [e for e in events if "Resolved" in e["action"]]
    assert len(resolves) == 2
    # The reporting application comes from the token audience, not the body.
    assert {e["source"] for e in resolves} == {"emehub", "qagent"}
    assert all(e["target"] == "claude:own" for e in resolves)
    # …and the audit trail itself never records the credential.
    assert TOKEN not in json.dumps(events)


def test_a_resolve_that_finds_nothing_is_still_audited(client, hub):
    client.get("/credentials/claude/resolve", headers=hub["a"])
    actions = [e["action"] for e in _credential_events(client, hub["a"])]
    assert any("found none" in a for a in actions)


def test_credential_management_is_audited(client, hub):
    upload_own(client, hub["a"])
    client.put("/credentials/claude", json={"credentials": "{}"}, headers=hub["a"])
    client.delete("/credentials/claude", headers=hub["a"])

    actions = [e["action"] for e in _credential_events(client, hub["a"])]
    assert any("Uploaded a personal" in a for a in actions)
    assert any("Rejected an invalid" in a for a in actions)
    assert any("Deleted their personal" in a for a in actions)


# ------------------------------------------------------ nothing else leaks it
def _api_routes(app):
    """Every ``APIRoute`` in the app, flattened.

    ``include_router`` nests routes under an ``_IncludedRouter`` in this FastAPI
    version, so a flat pass over ``app.routes`` silently finds nothing.
    """
    from fastapi.routing import APIRoute

    found = []
    stack = list(app.routes)
    seen: set[int] = set()
    while stack:
        route = stack.pop()
        if id(route) in seen:
            continue
        seen.add(id(route))
        if isinstance(route, APIRoute):
            found.append(route)
        stack.extend(getattr(route, "routes", []))
        included = getattr(route, "original_router", None)
        if included is not None:
            stack.extend(included.routes)
    return found


def test_only_the_resolve_response_model_can_carry_credential_material(app):
    """Structural, not behavioural: no other endpoint even has a field to put a
    credential in, so a mistake in a handler cannot serialise one."""
    routes = _api_routes(app)
    assert len(routes) > 10, "route discovery is broken — the assertion below would be vacuous"

    carriers = sorted(
        f"{sorted(route.methods)[0]} {route.path}"
        for route in routes
        if "credentials" in getattr(route.response_model, "model_fields", {})
    )
    assert carriers == ["GET /credentials/claude/resolve"]


def test_every_credential_route_declares_an_auth_guard(app):
    """The blanket ``CONTRACT`` dependency plus, on management routes, a
    stricter one of their own."""
    from app.deps_auth import require_admin, require_principal, require_user

    guards = {require_user, require_admin, require_principal}
    unguarded = []
    for route in _api_routes(app):
        if not route.path.startswith("/credentials/"):
            continue
        callables = {d.call for d in route.dependant.dependencies}
        for dependency in route.dependant.dependencies:
            callables.update(sub.call for sub in dependency.dependencies)
        if not (callables & guards):
            unguarded.append(f"{sorted(route.methods)} {route.path}")
    assert unguarded == []


def test_no_other_endpoint_returns_the_token(client, hub, agent_headers):
    """Behavioural backstop for the structural test above: exercise every
    credential endpoint and every identity/audit endpoint an agent can reach,
    and assert the token appears in exactly one response."""
    upload_shared(client, hub["admin"], creds_file(OTHER_TOKEN))
    upload_own(client, hub["a"], creds_file(TOKEN))

    responses = {
        "put own": upload_own(client, hub["a"], creds_file(TOKEN)),
        "get status": client.get("/credentials/claude", headers=hub["a"]),
        "put mode shared": client.put(
            "/credentials/claude/mode", json={"mode": "shared"}, headers=hub["a"]
        ),
        "put mode own": client.put(
            "/credentials/claude/mode", json={"mode": "own"}, headers=hub["a"]
        ),
        "post test": client.post("/credentials/claude/test", headers=hub["a"]),
        "put shared": upload_shared(client, hub["admin"], creds_file(OTHER_TOKEN)),
        "put refreshed": client.put(
            "/credentials/claude/refreshed",
            json={"credentials": creds_file(TOKEN, days=90)},
            headers=agent_headers(),
        ),
        "post usage": client.post(
            "/credentials/claude/usage", json={"model": "claude-x"}, headers=agent_headers()
        ),
        "get usage": client.get("/credentials/claude/usage", headers=hub["a"]),
        "get me": client.get("/me", headers=agent_headers()),
        "get audit": client.get("/audit/events", headers=hub["a"]),
        "get openapi": client.get("/openapi.json"),
    }
    leaks = [name for name, r in responses.items() if TOKEN in r.text or OTHER_TOKEN in r.text]
    assert leaks == []

    # …and the one endpoint that is supposed to.
    assert TOKEN in client.get("/credentials/claude/resolve", headers=hub["a"]).text


def test_the_token_is_never_logged(client, hub, caplog):
    """Not even truncated, not even at debug level."""
    import logging

    with caplog.at_level(logging.DEBUG):
        upload_own(client, hub["a"])
        client.get("/credentials/claude/resolve", headers=hub["a"])
        client.post("/credentials/claude/test", headers=hub["a"])
        client.put("/credentials/claude", json={"credentials": "{}"}, headers=hub["a"])
    for fragment in (TOKEN, TOKEN[:16], "sk-ant-ort01-refresh"):
        assert fragment not in caplog.text


# ------------------------------------------------------------------ posture
@pytest.mark.parametrize(
    ("method", "path", "body"),
    [
        ("get", "/credentials/claude", None),
        ("put", "/credentials/claude", {"credentials": creds_file()}),
        ("delete", "/credentials/claude", None),
        ("put", "/credentials/claude/mode", {"mode": "own"}),
        ("put", "/credentials/claude/shared", {"credentials": creds_file()}),
        ("delete", "/credentials/claude/shared", None),
        ("post", "/credentials/claude/test", None),
        ("get", "/credentials/claude/usage", None),
    ],
)
def test_an_agent_token_may_resolve_but_may_not_manage(
    client, hub, agent_headers, method, path, body
):
    """CONTRACT posture, tightened per route: ``aud: qagent`` is accepted by
    ``/resolve`` and refused by every management endpoint."""
    upload_own(client, hub["a"])
    kwargs = {"headers": agent_headers()}
    if body is not None:
        kwargs["json"] = body
    assert getattr(client, method)(path, **kwargs).status_code == 401

    assert client.get("/credentials/claude/resolve", headers=agent_headers()).status_code == 200


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("get", "/credentials/claude"),
        ("put", "/credentials/claude"),
        ("delete", "/credentials/claude"),
        ("get", "/credentials/claude/resolve"),
        ("put", "/credentials/claude/refreshed"),
        ("put", "/credentials/claude/shared"),
        ("delete", "/credentials/claude/shared"),
        ("post", "/credentials/claude/test"),
        ("post", "/credentials/claude/usage"),
        ("get", "/credentials/claude/usage"),
    ],
)
def test_nothing_is_reachable_unauthenticated(client, method, path):
    assert client.request(method.upper(), path).status_code == 401


# ------------------------------------------------------------------ rotation
def test_an_agent_posts_back_a_rotated_token(client, hub, agent_headers):
    upload_own(client, hub["a"], creds_file(TOKEN, days=1))
    rotated = creds_file(OTHER_TOKEN, days=60)

    response = client.put(
        "/credentials/claude/refreshed",
        json={"credentials": rotated},
        headers=agent_headers(),
    )
    assert response.json() == {"ok": True, "updated": True}
    assert (
        client.get("/credentials/claude/resolve", headers=hub["a"]).json()["credentials"]
        == rotated
    )


def test_a_stale_write_back_is_reported_as_not_updated(client, hub, agent_headers):
    fresh = creds_file(TOKEN, days=60)
    upload_own(client, hub["a"], fresh)

    response = client.put(
        "/credentials/claude/refreshed",
        json={"credentials": creds_file(OTHER_TOKEN, days=1)},
        headers=agent_headers(),
    )
    assert response.json() == {"ok": True, "updated": False}
    assert (
        client.get("/credentials/claude/resolve", headers=hub["a"]).json()["credentials"]
        == fresh
    )


# ------------------------------------------------------------------ usage
def test_usage_is_recorded_against_the_calling_principal(client, hub, agent_headers):
    upload_own(client, hub["a"])
    response = client.post(
        "/credentials/claude/usage",
        json={
            "model": "claude-opus-4-8",
            "inputTokens": 1200,
            "outputTokens": 300,
            "cacheReadTokens": 50,
            "cacheWriteTokens": 25,
            "costUsd": 0.42,
            "durationMs": 1800,
            "action": "test-case-generator",
            "externalRef": "run-7",
        },
        headers=agent_headers(),
    )
    assert response.status_code == 201

    stats = client.get("/credentials/claude/usage", headers=hub["a"]).json()
    assert stats["requestsToday"] == 1
    assert stats["avgLatencyMs"] == 1800
    assert stats["costMonth"] == 0.42
    assert stats["weekTokens"] == 1575
    assert stats["breakdown"] == {
        "input": 1200,
        "output": 300,
        "cacheRead": 50,
        "cacheWrite": 25,
    }


def test_usage_is_scoped_to_its_owner(client, hub, agent_headers):
    client.post(
        "/credentials/claude/usage",
        json={"inputTokens": 999, "costUsd": 5.0},
        headers=agent_headers("member-a@emesoft.net"),
    )
    mine = client.get("/credentials/claude/usage", headers=hub["a"]).json()
    theirs = client.get("/credentials/claude/usage", headers=hub["b"]).json()
    assert mine["costMonth"] == 5.0
    assert theirs["costMonth"] == 0.0
    assert theirs["requestsToday"] == 0


def test_usage_records_which_credential_the_call_ran_under(client, hub, agent_headers):
    from app.models.claude_usage import ClaudeUsage

    upload_shared(client, hub["admin"])
    client.post("/credentials/claude/usage", json={}, headers=agent_headers())

    import app.db as db_module

    session = db_module.SessionLocal()
    try:
        row = session.query(ClaudeUsage).one()
        assert row.credential_source == "shared"
        assert row.source == "qagent"
    finally:
        session.close()
