"""``POST /auth/agent-token`` — the cross-app sign-in hand-off (ADR 0008).

An agent served from a sibling subdomain calls this from the browser with the
shared refresh cookie and gets an access token for *its own* audience only.

The load-bearing property is that it **does not rotate** the refresh token.
``/auth/refresh`` does, and a rotating credential shared by two SPAs races: the
silent refresh that lands second presents a dead token and logs a live session
out. ``test_minting_does_not_rotate_the_refresh_token`` is the regression guard
for that, and it is the reason this endpoint exists at all.
"""

from __future__ import annotations

import pytest

from app.config import AUDIENCE_DAGENT, AUDIENCE_HUB, AUDIENCE_QAGENT
from app.deps_auth import CSRF_COOKIE, CSRF_HEADER, REFRESH_COOKIE
from app.services import auth_service

EMAIL = "handoff@emesoft.net"
PASSWORD = "password12345"


def _csrf_headers(client):
    return {CSRF_HEADER: client.cookies.get(CSRF_COOKIE)}


@pytest.fixture
def signed_in(client, make_user):
    """A logged-in browser session: refresh + CSRF cookies are on the client."""
    make_user(EMAIL, PASSWORD)
    response = client.post("/auth/login", json={"email": EMAIL, "password": PASSWORD})
    assert response.status_code == 200, response.text
    return response.json()


# ------------------------------------------------------------------ happy path
def test_mints_a_token_for_the_requested_agent_audience(client, signed_in):
    response = client.post(
        "/auth/agent-token",
        json={"audience": AUDIENCE_QAGENT},
        headers=_csrf_headers(client),
    )
    assert response.status_code == 200, response.text
    body = response.json()

    assert body["audience"] == AUDIENCE_QAGENT
    assert body["user"]["email"] == EMAIL
    claims = auth_service.decode_access_token(body["accessToken"], AUDIENCE_QAGENT)
    assert claims["aud"] == AUDIENCE_QAGENT
    assert claims["email"] == EMAIL


def test_the_minted_token_carries_the_same_session_as_the_login(client, signed_in):
    """``sid`` is the hub session, so revoking it at the hub kills the agent too."""
    response = client.post(
        "/auth/agent-token",
        json={"audience": AUDIENCE_QAGENT},
        headers=_csrf_headers(client),
    )
    minted = auth_service.decode_access_token(response.json()["accessToken"], AUDIENCE_QAGENT)
    hub_login = auth_service.decode_access_token(signed_in["accessToken"], AUDIENCE_HUB)
    assert minted["sid"] == hub_login["sid"]


def test_the_response_leaks_no_refresh_material(client, signed_in):
    response = client.post(
        "/auth/agent-token",
        json={"audience": AUDIENCE_QAGENT},
        headers=_csrf_headers(client),
    )
    assert set(response.json()) == {"accessToken", "audience", "expiresIn", "user"}
    # No Set-Cookie at all: this endpoint reads the session, it never re-issues it.
    assert "set-cookie" not in {k.lower() for k in response.headers}


# ----------------------------------------------------- the reason this endpoint exists
def test_minting_does_not_rotate_the_refresh_token(client, signed_in):
    """The whole design in one assertion.

    If this ever fails, two apps sharing the cookie will race on silent refresh
    and log each other out. Do not "fix" it by updating the expectation.
    """
    before = client.cookies.get(REFRESH_COOKIE)

    for _ in range(3):
        assert (
            client.post(
                "/auth/agent-token",
                json={"audience": AUDIENCE_QAGENT},
                headers=_csrf_headers(client),
            ).status_code
            == 200
        )

    assert client.cookies.get(REFRESH_COOKIE) == before
    # And the un-rotated token still works on the path that *does* rotate.
    assert client.post("/auth/refresh", headers=_csrf_headers(client)).status_code == 200


def test_refresh_still_rotates(client, signed_in):
    """Guard the converse: minting must not have made /auth/refresh non-rotating."""
    before = client.cookies.get(REFRESH_COOKIE)
    assert client.post("/auth/refresh", headers=_csrf_headers(client)).status_code == 200
    assert client.cookies.get(REFRESH_COOKIE) != before


# ------------------------------------------------------------------ audience rules
def test_the_hub_audience_is_refused(client, signed_in):
    """An agent origin must not be able to mint credentials for hub-only routes."""
    response = client.post(
        "/auth/agent-token",
        json={"audience": AUDIENCE_HUB},
        headers=_csrf_headers(client),
    )
    assert response.status_code == 400
    assert "agent" in response.json()["detail"].lower()


def test_an_unregistered_audience_is_refused(client, signed_in, monkeypatch):
    from app import config as config_module

    monkeypatch.setattr(config_module.settings, "agent_dagent_url", "")
    response = client.post(
        "/auth/agent-token",
        json={"audience": AUDIENCE_DAGENT},
        headers=_csrf_headers(client),
    )
    assert response.status_code == 400
    assert AUDIENCE_DAGENT in response.json()["detail"]


def test_an_unknown_audience_is_refused(client, signed_in):
    response = client.post(
        "/auth/agent-token",
        json={"audience": "not-an-agent"},
        headers=_csrf_headers(client),
    )
    assert response.status_code == 400


def test_a_minted_token_is_not_accepted_for_another_audience(client, signed_in):
    token = client.post(
        "/auth/agent-token",
        json={"audience": AUDIENCE_QAGENT},
        headers=_csrf_headers(client),
    ).json()["accessToken"]

    with pytest.raises(auth_service.AuthError):
        auth_service.decode_access_token(token, AUDIENCE_DAGENT)
    # And it does not open hub-only routes.
    assert client.get("/auth/sessions", headers={"Authorization": f"Bearer {token}"}).status_code in (
        401,
        403,
    )


# ------------------------------------------------------------------ session & CSRF
def test_requires_the_csrf_header(client, signed_in):
    assert client.post("/auth/agent-token", json={"audience": AUDIENCE_QAGENT}).status_code == 403
    assert (
        client.post(
            "/auth/agent-token",
            json={"audience": AUDIENCE_QAGENT},
            headers={CSRF_HEADER: "wrong"},
        ).status_code
        == 403
    )


def test_without_a_refresh_cookie_is_401(client):
    response = client.post(
        "/auth/agent-token",
        json={"audience": AUDIENCE_QAGENT},
        headers={CSRF_HEADER: "anything"},
    )
    assert response.status_code == 401


def test_a_revoked_session_cannot_mint(client, signed_in):
    """Signing out at the hub must immediately stop new agent hand-offs."""
    logout = client.post(
        "/auth/logout",
        headers={
            **_csrf_headers(client),
            "Authorization": f"Bearer {signed_in['accessToken']}",
        },
    )
    assert logout.status_code == 200, logout.text
    response = client.post(
        "/auth/agent-token",
        json={"audience": AUDIENCE_QAGENT},
        headers={CSRF_HEADER: "anything"},
    )
    assert response.status_code in (401, 403)


def test_a_deactivated_user_cannot_mint(client, signed_in, db_session):
    from app.models.user import User

    user = db_session.query(User).filter(User.email == EMAIL).one()
    user.is_active = False
    db_session.add(user)
    db_session.commit()

    response = client.post(
        "/auth/agent-token",
        json={"audience": AUDIENCE_QAGENT},
        headers=_csrf_headers(client),
    )
    assert response.status_code == 401


# ------------------------------------------------------------------ CORS config
# The hand-off is cross-origin, so the agent's origin has to be allowlisted.
# EMEHUB_CORS_ORIGINS is operator-facing config set by hand once per deployment,
# and docker-compose passes it as ${EMEHUB_CORS_ORIGINS:-} — so an empty string
# reaches the parser whenever the operator has not set it.
@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ('["https://a.test","https://b.test"]', ["https://a.test", "https://b.test"]),
        ("https://a.test,https://b.test", ["https://a.test", "https://b.test"]),
        (" https://a.test , https://b.test ", ["https://a.test", "https://b.test"]),
        ("https://a.test", ["https://a.test"]),
    ],
)
def test_cors_origins_accepts_json_or_a_comma_separated_list(monkeypatch, raw, expected):
    from app.config import Settings

    monkeypatch.setenv("EMEHUB_CORS_ORIGINS", raw)
    assert Settings().cors_origins == expected


@pytest.mark.parametrize("raw", ["", "   "])
def test_an_empty_cors_value_means_unset_not_deny_everything(monkeypatch, raw):
    """Declaring the variable in compose must not break `npm run dev`."""
    from app.config import DEFAULT_CORS_ORIGINS, Settings

    monkeypatch.setenv("EMEHUB_CORS_ORIGINS", raw)
    assert Settings().cors_origins == list(DEFAULT_CORS_ORIGINS)
