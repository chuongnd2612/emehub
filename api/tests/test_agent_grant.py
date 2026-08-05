"""Run-scoped Claude-credential grants (ADR 0009).

A grant lives hours rather than 15 minutes, so almost every test here is a
**negative** one: the value of the design is entirely in what a grant cannot do.
The positive case is one endpoint working; the design is everything else refusing
it.
"""

from __future__ import annotations

import jwt
import pytest

from app.config import AUDIENCE_DAGENT, AUDIENCE_HUB, AUDIENCE_QAGENT, settings
from app.services import auth_service
from tests.test_claude_credentials import TOKEN, creds_file

PASSWORD = "password12345"


@pytest.fixture
def upload_credential(client, auth_headers):
    """Give a user an own Claude credential, through the real endpoint."""

    def _upload(email: str):
        headers = auth_headers(email, PASSWORD)
        response = client.put(
            "/credentials/claude",
            json={"credentials": creds_file(TOKEN), "label": "laptop"},
            headers=headers,
        )
        assert response.status_code in (200, 201), response.text

    return _upload


@pytest.fixture
def agent(client, make_user, login):
    """A user plus a qagent access token and a grant minted from it."""
    user = make_user("granted@emesoft.net", "password12345")
    tokens = login("granted@emesoft.net", "password12345")["tokens"]
    access = {"Authorization": f"Bearer {tokens[AUDIENCE_QAGENT]}"}
    minted = client.post("/auth/agent-grant", json={"runId": "run-77"}, headers=access)
    assert minted.status_code == 201, minted.text
    grant = {"Authorization": f"Bearer {minted.json()['grant']}"}
    return user, access, grant, minted.json()


# ---------------------------------------------------------------- minting
def test_an_agent_token_mints_a_grant(agent):
    _, _, _, body = agent
    assert body["audience"] == AUDIENCE_QAGENT
    assert body["scope"] == auth_service.SCOPE_CLAUDE_CREDENTIAL
    assert body["runId"] == "run-77"
    assert body["expiresIn"] == settings.agent_grant_ttl_minutes * 60


def test_the_grant_carries_the_session_and_the_agent_it_was_minted_for(agent):
    user, access, _, body = agent
    claims = jwt.decode(
        body["grant"],
        settings.jwt_secret,
        algorithms=["HS256"],
        audience=auth_service.AUDIENCE_GRANT,
        issuer="emehub",
    )
    assert claims["sub"] == str(user.id)
    assert claims["agt"] == AUDIENCE_QAGENT
    assert claims["scp"] == auth_service.SCOPE_CLAUDE_CREDENTIAL
    assert claims["run"] == "run-77"
    # Bound to the same hub session — this is what keeps revocation working.
    assert claims["sid"]


def test_minting_requires_authentication(client):
    assert client.post("/auth/agent-grant", json={"runId": "x"}).status_code == 401


def test_the_hub_audience_cannot_mint_a_grant(client, make_user, auth_headers):
    """The hub SPA has a session and a rotating refresh token. Handing a browser
    origin a long-lived credential-scoped token would be strictly worse than the
    15-minute token it already holds."""
    make_user("hubmint@emesoft.net", "password12345")
    headers = auth_headers("hubmint@emesoft.net", "password12345")
    response = client.post("/auth/agent-grant", json={"runId": "x"}, headers=headers)
    assert response.status_code == 400
    assert "agent, not the hub" in response.json()["detail"]


def test_a_grant_cannot_mint_another_grant(client, agent):
    """No grant->grant chain: a compromised grant expires and stops."""
    _, _, grant, _ = agent
    assert client.post("/auth/agent-grant", json={"runId": "x"}, headers=grant).status_code == 401


def test_a_run_id_is_optional(client, make_user, login):
    make_user("norun@emesoft.net", "password12345")
    tokens = login("norun@emesoft.net", "password12345")["tokens"]
    headers = {"Authorization": f"Bearer {tokens[AUDIENCE_DAGENT]}"}
    body = client.post("/auth/agent-grant", json={}, headers=headers).json()
    assert body["runId"] == ""
    assert body["audience"] == AUDIENCE_DAGENT


# ------------------------------------------------- what a grant may do (only)
def test_a_grant_resolves_a_credential(client, agent, upload_credential):
    """The one thing it is for."""
    _, _, grant, _ = agent
    upload_credential("granted@emesoft.net")
    response = client.get("/credentials/claude/resolve", headers=grant)
    assert response.status_code == 200, response.text
    assert TOKEN in response.json()["credentials"]


def test_a_grant_reaches_refreshed_and_usage(client, agent, upload_credential):
    _, _, grant, _ = agent
    upload_credential("granted@emesoft.net")
    refreshed = client.put(
        "/credentials/claude/refreshed",
        json={"credentials": creds_file("rotated-token")},
        headers=grant,
    )
    assert refreshed.status_code != 401, refreshed.text
    usage = client.post(
        "/credentials/claude/usage",
        json={"model": "claude-opus-5", "inputTokens": 10, "outputTokens": 5},
        headers=grant,
    )
    assert usage.status_code != 401, usage.text


# --------------------------------------------------- what a grant may NOT do
@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("get", "/me"),
        ("get", "/projects"),
        ("get", "/tickets"),
        ("get", "/connections"),
        ("get", "/agents"),
        ("get", "/auth/me"),
        ("get", "/auth/sessions"),
        ("get", "/credentials/claude"),
        ("get", "/credentials/claude/usage"),
        ("get", "/audit/events"),
    ],
)
def test_a_grant_is_refused_everywhere_except_the_credential_routes(
    client, agent, method, path
):
    """The narrowness is the whole security argument, so assert it per route."""
    _, _, grant, _ = agent
    assert getattr(client, method)(path, headers=grant).status_code == 401, path


def test_a_grant_is_refused_for_writes_an_agent_token_may_do(client, agent):
    _, _, grant, _ = agent
    assert client.post("/audit/events", json={"category": "run", "action": "x"}, headers=grant).status_code == 401
    assert client.post("/tickets/sync", json={"providerKind": "ado"}, headers=grant).status_code == 401


def test_a_grant_cannot_manage_a_credential(client, agent):
    """It reaches the router, and the per-route require_user still refuses it."""
    _, _, grant, _ = agent
    assert client.put(
        "/credentials/claude", json={"credentials": {"claudeAiOauth": {}}}, headers=grant
    ).status_code == 401
    assert client.delete("/credentials/claude", headers=grant).status_code == 401
    assert client.put("/credentials/claude/mode", json={"preferShared": True}, headers=grant).status_code == 401


# ------------------------------------------------------------- structurally
def test_a_grant_is_not_an_access_token(client, agent):
    """Structural, not routed: the decoders themselves must refuse it."""
    _, _, _, body = agent
    grant = body["grant"]
    with pytest.raises(auth_service.AuthError):
        auth_service.decode_any_registered(grant)
    with pytest.raises(auth_service.AuthError):
        auth_service.decode_access_token(grant, AUDIENCE_QAGENT)
    with pytest.raises(auth_service.AuthError):
        auth_service.decode_access_token(grant, AUDIENCE_HUB)
    assert auth_service.access_token_valid(grant) is False
    assert auth_service.agent_grant_valid(grant) is True


def test_an_access_token_is_not_a_grant(client, make_user, login):
    make_user("nottagrant@emesoft.net", "password12345")
    tokens = login("nottagrant@emesoft.net", "password12345")["tokens"]
    with pytest.raises(auth_service.AuthError):
        auth_service.decode_agent_grant(tokens[AUDIENCE_QAGENT])
    assert auth_service.agent_grant_valid(tokens[AUDIENCE_QAGENT]) is False


def test_the_grant_audience_is_never_registerable():
    """If it were, a grant would be accepted as an access token."""
    assert auth_service.AUDIENCE_GRANT not in settings.registered_audiences


def test_a_grant_missing_its_scope_is_refused(agent, make_user):
    """A token in the grant audience without `scp` must not be treated as
    unscoped — it would be a grant that may do anything."""
    _, _, _, body = agent
    claims = jwt.decode(
        body["grant"],
        settings.jwt_secret,
        algorithms=["HS256"],
        audience=auth_service.AUDIENCE_GRANT,
        issuer="emehub",
    )
    claims.pop("scp")
    forged = jwt.encode(claims, settings.jwt_secret, algorithm="HS256")
    with pytest.raises(auth_service.AuthError, match="scope"):
        auth_service.decode_agent_grant(forged)


def test_a_grant_naming_a_deregistered_agent_stops_working(client, agent, monkeypatch):
    import app.config as config_module

    _, _, grant, _ = agent
    monkeypatch.setattr(config_module.settings, "agent_qagent_url", "")
    assert client.get("/credentials/claude/resolve", headers=grant).status_code == 401


def test_a_grant_signed_with_another_secret_is_refused(agent):
    _, _, _, body = agent
    claims = jwt.decode(
        body["grant"],
        settings.jwt_secret,
        algorithms=["HS256"],
        audience=auth_service.AUDIENCE_GRANT,
        issuer="emehub",
    )
    forged = jwt.encode(claims, "a-different-secret-entirely", algorithm="HS256")
    with pytest.raises(auth_service.AuthError):
        auth_service.decode_agent_grant(forged)


def test_an_expired_grant_is_refused(client, agent, monkeypatch):
    """A grant that has run out must fail closed, like any other expired token."""
    from datetime import timedelta

    monkeypatch.setattr(auth_service, "grant_ttl", lambda: timedelta(seconds=-1))
    expired = auth_service.create_agent_grant(
        _StubUser(1, "granted@emesoft.net"),
        "any-sid",
        agent_audience=AUDIENCE_QAGENT,
        run_id="r",
    )
    assert auth_service.agent_grant_valid(expired) is False
    response = client.get(
        "/credentials/claude/resolve", headers={"Authorization": f"Bearer {expired}"}
    )
    assert response.status_code == 401


class _StubUser:
    """Minimal stand-in for the two attributes ``create_agent_grant`` reads."""

    def __init__(self, id_: int, email: str) -> None:
        self.id = id_
        self.email = email
        self.role = "member"


# ---------------------------------------------------- revocation still works
def test_revoking_the_hub_session_kills_a_live_grant(client, make_user, login, db_session):
    """INTEGRATION.md §2 — "revoking the session kills every agent" — must hold
    for grants verbatim, or a grant would be an *unrevocable* credential.

    One login, so the hub token and the agent token share one ``sid``; the grant
    is minted from the agent token and inherits that same ``sid``. Logging out with
    the hub token therefore revokes the session the grant is bound to.
    """
    make_user("revoked@emesoft.net", PASSWORD)
    tokens = login("revoked@emesoft.net", PASSWORD)["tokens"]
    agent_headers = {"Authorization": f"Bearer {tokens[AUDIENCE_QAGENT]}"}
    hub_headers = {"Authorization": f"Bearer {tokens[AUDIENCE_HUB]}"}

    grant = client.post("/auth/agent-grant", json={"runId": "r"}, headers=agent_headers).json()[
        "grant"
    ]
    grant_headers = {"Authorization": f"Bearer {grant}"}
    # Live before revocation (404 = no credential configured, which is still a
    # pass through the auth layer — the point here is that it is not a 401).
    assert client.get("/credentials/claude/resolve", headers=grant_headers).status_code in (
        200,
        404,
    )

    logged_out = client.post("/auth/logout", headers=hub_headers)
    assert logged_out.status_code in (200, 204), logged_out.text

    # The grant itself is still cryptographically valid and unexpired…
    assert auth_service.agent_grant_valid(grant) is True
    # …and is refused anyway, because the session behind it is gone.
    assert client.get("/credentials/claude/resolve", headers=grant_headers).status_code == 401


def test_a_deactivated_users_grant_stops_working(client, agent, db_session):
    user, _, grant, _ = agent
    user.is_active = False
    db_session.add(user)
    db_session.commit()
    assert client.get("/credentials/claude/resolve", headers=grant).status_code == 401


# ------------------------------------------------------------------- config
def test_the_grant_ttl_is_capped():
    from app.config import GRANT_TTL_CAP_MINUTES, Settings

    with pytest.raises(ValueError, match="between 1 and"):
        Settings(
            jwt_secret="a", encryption_key="b", agent_grant_ttl_minutes=GRANT_TTL_CAP_MINUTES + 1
        )
    with pytest.raises(ValueError, match="between 1 and"):
        Settings(jwt_secret="a", encryption_key="b", agent_grant_ttl_minutes=0)


def test_the_default_ttl_is_longer_than_an_access_token_and_within_the_cap():
    from app.config import GRANT_TTL_CAP_MINUTES

    assert settings.agent_grant_ttl_minutes > settings.access_token_ttl_minutes
    assert settings.agent_grant_ttl_minutes <= GRANT_TTL_CAP_MINUTES


# --------------------------------------------------------------------- audit
def test_minting_is_audited_with_the_agent_and_the_run(client, make_user, login, db_session):
    from app.models.audit import AuditLog

    make_user("auditgrant@emesoft.net", "password12345")
    tokens = login("auditgrant@emesoft.net", "password12345")["tokens"]
    headers = {"Authorization": f"Bearer {tokens[AUDIENCE_QAGENT]}"}
    client.post("/auth/agent-grant", json={"runId": "run-123"}, headers=headers)

    event = (
        db_session.query(AuditLog)
        .filter(AuditLog.action == "Minted a credential grant")
        .order_by(AuditLog.id.desc())
        .first()
    )
    assert event is not None
    assert event.source == AUDIENCE_QAGENT
    assert "run-123" in event.target


def test_using_a_grant_is_audited_like_any_other_resolve(
    client, agent, upload_credential, db_session
):
    """So a resolved credential is traceable to the run that asked for it."""
    from app.models.audit import AuditLog

    _, _, grant, _ = agent
    upload_credential("granted@emesoft.net")
    client.get("/credentials/claude/resolve", headers=grant)

    event = (
        db_session.query(AuditLog)
        .filter(AuditLog.category == "credential", AuditLog.action.like("Resolved%"))
        .order_by(AuditLog.id.desc())
        .first()
    )
    assert event is not None
    assert event.source == AUDIENCE_QAGENT
