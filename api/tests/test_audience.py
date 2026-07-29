"""Audience scoping — the thing QAgent does not do (INTEGRATION.md §2).

Three properties:

1. the claim set is exactly what the contract says, with a ``kid`` header;
2. a token for one audience is refused where another is required;
3. an audience the operator has not registered receives no token at all.
"""

from __future__ import annotations

import jwt
import pytest

from app.config import AUDIENCE_DAGENT, AUDIENCE_HUB, AUDIENCE_QAGENT
from app.services import auth_service


def _claims(token: str) -> dict:
    return jwt.decode(token, options={"verify_signature": False})


# ---------------------------------------------------------------- claim set
def test_access_token_carries_exactly_the_contract_claims(client, make_user, login):
    make_user("claims@emesoft.net", "password12345", role="admin")
    token = login("claims@emesoft.net", "password12345")["accessToken"]

    claims = _claims(token)
    assert set(claims) == {"sub", "email", "role", "sid", "aud", "iss", "iat", "exp"}
    assert claims["email"] == "claims@emesoft.net"
    assert claims["role"] == "admin"
    assert claims["aud"] == AUDIENCE_HUB
    assert claims["iss"] == "emehub"
    assert claims["sub"].isdigit()
    assert len(claims["sid"]) == 32
    # 15 minutes, per the contract.
    assert claims["exp"] - claims["iat"] == 15 * 60


def test_access_token_has_a_kid_header_from_the_very_first_token(client, make_user, login):
    """INTEGRATION.md › Key distribution: the ``kid`` must be present now so the
    Phase-3 move to RS256 + JWKS is not a breaking change."""
    make_user("kid@emesoft.net", "password12345")
    token = login("kid@emesoft.net", "password12345")["accessToken"]

    header = jwt.get_unverified_header(token)
    assert header["kid"] == auth_service.ACCESS_TOKEN_KID
    assert header["alg"] == "HS256"


def test_kid_does_not_expose_the_signing_secret(client):
    import app.config as config_module

    assert config_module.settings.jwt_secret not in auth_service.ACCESS_TOKEN_KID


# ---------------------------------------------------------------- per-audience issue
def test_login_issues_one_token_per_registered_audience(client, make_user, login):
    make_user("multi@emesoft.net", "password12345")
    body = login("multi@emesoft.net", "password12345")

    assert set(body["tokens"]) == {AUDIENCE_HUB, AUDIENCE_QAGENT, AUDIENCE_DAGENT}
    for audience, token in body["tokens"].items():
        assert _claims(token)["aud"] == audience
    assert body["accessToken"] == body["tokens"][AUDIENCE_HUB]


def test_refresh_issues_a_new_token_per_audience(client, make_user, login):
    from app.deps_auth import CSRF_COOKIE, CSRF_HEADER

    make_user("refresh-aud@emesoft.net", "password12345")
    before = login("refresh-aud@emesoft.net", "password12345")["tokens"]

    response = client.post(
        "/auth/refresh", headers={CSRF_HEADER: client.cookies.get(CSRF_COOKIE)}
    )
    assert response.status_code == 200, response.text
    after = response.json()["tokens"]
    assert set(after) == set(before)
    for audience, token in after.items():
        assert _claims(token)["aud"] == audience


def test_refresh_can_ask_for_a_subset(client, make_user, login):
    from app.deps_auth import CSRF_COOKIE, CSRF_HEADER

    make_user("subset@emesoft.net", "password12345")
    login("subset@emesoft.net", "password12345")

    response = client.post(
        "/auth/refresh",
        json={"audiences": [AUDIENCE_QAGENT]},
        headers={CSRF_HEADER: client.cookies.get(CSRF_COOKIE)},
    )
    assert response.status_code == 200
    # The hub's own audience is always included so the caller can talk to us.
    assert set(response.json()["tokens"]) == {AUDIENCE_QAGENT, AUDIENCE_HUB}


# ---------------------------------------------------------------- cross-audience refusal
def test_a_qagent_token_is_refused_where_dagent_is_required(client, make_user, login):
    make_user("cross@emesoft.net", "password12345")
    qagent_token = login("cross@emesoft.net", "password12345")["tokens"][AUDIENCE_QAGENT]

    # Valid for its own audience…
    assert auth_service.decode_access_token(qagent_token, AUDIENCE_QAGENT)["aud"] == AUDIENCE_QAGENT
    # …and refused for another agent's.
    with pytest.raises(auth_service.AuthError):
        auth_service.decode_access_token(qagent_token, AUDIENCE_DAGENT)
    assert auth_service.access_token_valid(qagent_token, AUDIENCE_DAGENT) is False


def test_a_qagent_token_cannot_manage_the_hub(client, make_user, login):
    """Hub management endpoints are ``aud: emehub`` only — an agent token can
    read identity but not administer the hub."""
    make_user("agentonly@emesoft.net", "password12345", role="admin")
    tokens = login("agentonly@emesoft.net", "password12345")["tokens"]
    headers = {"Authorization": f"Bearer {tokens[AUDIENCE_QAGENT]}"}

    assert client.get("/auth/me", headers=headers).status_code == 401
    assert client.get("/auth/users", headers=headers).status_code == 401
    # …but the contract endpoint agents actually consume works.
    assert client.get("/me", headers=headers).status_code == 200


def test_the_hub_token_is_accepted_on_contract_endpoints(client, make_user, auth_headers):
    make_user("hubtoken@emesoft.net", "password12345")
    headers = auth_headers("hubtoken@emesoft.net", "password12345")
    assert client.get("/me", headers=headers).status_code == 200


# ---------------------------------------------------------------- unregistered audiences
@pytest.fixture
def no_dagent(monkeypatch):
    """Unregister DAgent by clearing its URL, as an operator would."""
    import app.config as config_module

    monkeypatch.setattr(config_module.settings, "agent_dagent_url", "")
    return config_module.settings


def test_an_unregistered_audience_gets_no_token(client, make_user, no_dagent):
    assert AUDIENCE_DAGENT not in no_dagent.registered_audiences

    make_user("unreg@emesoft.net", "password12345")
    response = client.post(
        "/auth/login",
        json={
            "email": "unreg@emesoft.net",
            "password": "password12345",
            "audiences": [AUDIENCE_DAGENT],
        },
    )
    assert response.status_code == 400
    assert "dagent" in response.json()["detail"]


def test_an_unregistered_audience_poisons_the_whole_bundle(client, make_user, no_dagent):
    """One bad audience means no tokens at all, not a partial set."""
    make_user("partial@emesoft.net", "password12345")
    response = client.post(
        "/auth/login",
        json={
            "email": "partial@emesoft.net",
            "password": "password12345",
            "audiences": [AUDIENCE_QAGENT, AUDIENCE_DAGENT],
        },
    )
    assert response.status_code == 400
    assert "tokens" not in response.json()


def test_default_bundle_omits_an_unregistered_agent(client, make_user, login, no_dagent):
    make_user("default@emesoft.net", "password12345")
    body = login("default@emesoft.net", "password12345")
    assert set(body["tokens"]) == {AUDIENCE_HUB, AUDIENCE_QAGENT}


def test_service_layer_refuses_to_mint_for_an_unregistered_audience(
    db_session, make_user, no_dagent
):
    user = make_user("svc@emesoft.net", "password12345")
    with pytest.raises(auth_service.UnregisteredAudience):
        auth_service.create_access_token(user, "s" * 32, AUDIENCE_DAGENT)
    with pytest.raises(auth_service.UnregisteredAudience):
        auth_service.create_access_tokens(user, "s" * 32, [AUDIENCE_QAGENT, AUDIENCE_DAGENT])


def test_a_previously_issued_token_stops_validating_once_deregistered(
    client, make_user, login, monkeypatch
):
    import app.config as config_module

    make_user("dereg@emesoft.net", "password12345")
    dagent_token = login("dereg@emesoft.net", "password12345")["tokens"][AUDIENCE_DAGENT]
    assert auth_service.access_token_valid(dagent_token) is True

    monkeypatch.setattr(config_module.settings, "agent_dagent_url", "")
    assert auth_service.access_token_valid(dagent_token) is False
    assert (
        client.get("/me", headers={"Authorization": f"Bearer {dagent_token}"}).status_code
        == 401
    )


def test_mfa_and_reset_tokens_live_outside_the_registered_audiences(db_session, make_user):
    user = make_user("kinds@emesoft.net", "password12345")
    for token in (auth_service.create_mfa_token(user), auth_service.create_reset_token(user)):
        assert auth_service.access_token_valid(token) is False
        with pytest.raises(auth_service.AuthError):
            auth_service.decode_access_token(token)
