"""Login, the guard, refresh, profile and password flows."""

from __future__ import annotations

import jwt

from app.deps_auth import CSRF_COOKIE, CSRF_HEADER, REFRESH_COOKIE
from app.services import auth_service


def _csrf_headers(client):
    return {CSRF_HEADER: client.cookies.get(CSRF_COOKIE)}


# ---------------------------------------------------------------- the guard
def test_protected_route_refuses_a_tokenless_request(client):
    assert client.get("/me").status_code == 401
    assert client.get("/auth/me").status_code == 401
    assert client.get("/audit/events").status_code == 401


def test_health_is_public(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_guard_refuses_a_garbage_bearer(client):
    response = client.get("/me", headers={"Authorization": "Bearer not-a-token"})
    assert response.status_code == 401


def test_guard_refuses_a_token_signed_with_the_wrong_secret(client, make_user):
    user = make_user("forge@emesoft.net", "password12345")
    forged = jwt.encode(
        {
            "sub": str(user.id),
            "email": user.email,
            "role": user.role,
            "sid": "x" * 32,
            "aud": "emehub",
            "iss": "emehub",
            "iat": 1785312000,
            "exp": 4102444800,
        },
        "the-wrong-secret",
        algorithm="HS256",
    )
    assert client.get("/me", headers={"Authorization": f"Bearer {forged}"}).status_code == 401


def test_there_is_no_way_to_disable_auth(client):
    """CLAUDE.md › Never fail open. No setting may turn the guard into a
    passthrough — assert the switch simply does not exist."""
    import app.config as config_module
    from app import security

    assert not hasattr(config_module.settings, "auth_required")
    source = __import__("pathlib").Path(security.__file__).read_text(encoding="utf-8")
    assert "auth_required" not in source.split('"""', 2)[-1]


# ---------------------------------------------------------------- login
def test_login_returns_tokens_and_sets_cookies(client, make_user):
    make_user("admin@emesoft.net", "supersecret1", role="admin")
    response = client.post(
        "/auth/login",
        json={"email": "admin@emesoft.net", "password": "supersecret1", "remember": True},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["accessToken"]
    assert body["user"]["email"] == "admin@emesoft.net"
    assert body["mfaRequired"] is False
    assert client.cookies.get(REFRESH_COOKIE)
    assert client.cookies.get(CSRF_COOKIE)


def test_login_is_case_insensitive_on_email(client, make_user):
    make_user("Mixed@Emesoft.net", "password12345")
    response = client.post(
        "/auth/login", json={"email": "MIXED@emesoft.NET", "password": "password12345"}
    )
    assert response.status_code == 200


def test_login_rejects_a_bad_password_with_the_same_message_as_a_missing_user(
    client, make_user
):
    make_user("real@emesoft.net", "password12345")
    wrong = client.post(
        "/auth/login", json={"email": "real@emesoft.net", "password": "nope"}
    )
    missing = client.post(
        "/auth/login", json={"email": "ghost@emesoft.net", "password": "nope"}
    )
    assert wrong.status_code == missing.status_code == 401
    assert wrong.json()["detail"] == missing.json()["detail"]


def test_login_refuses_an_inactive_user(client, make_user):
    make_user("gone@emesoft.net", "password12345", active=False)
    response = client.post(
        "/auth/login", json={"email": "gone@emesoft.net", "password": "password12345"}
    )
    assert response.status_code == 401


def test_login_refuses_an_invited_user_with_no_password(client, make_user):
    make_user("invited@emesoft.net", password="")
    response = client.post(
        "/auth/login", json={"email": "invited@emesoft.net", "password": ""}
    )
    assert response.status_code == 401


def test_login_stamps_last_active(client, make_user, db_session):
    user = make_user("active@emesoft.net", "password12345")
    assert user.last_active is None
    client.post(
        "/auth/login", json={"email": "active@emesoft.net", "password": "password12345"}
    )
    db_session.refresh(user)
    assert user.last_active is not None


def test_no_response_ever_contains_the_refresh_token(client, make_user):
    make_user("cookie@emesoft.net", "password12345")
    response = client.post(
        "/auth/login", json={"email": "cookie@emesoft.net", "password": "password12345"}
    )
    refresh = client.cookies.get(REFRESH_COOKIE)
    assert refresh and refresh not in response.text


def test_refresh_token_is_stored_only_as_a_sha256_hash(client, make_user, db_session):
    from app.models.session import Session as AuthSession

    make_user("hash@emesoft.net", "password12345")
    client.post(
        "/auth/login", json={"email": "hash@emesoft.net", "password": "password12345"}
    )
    plaintext = client.cookies.get(REFRESH_COOKIE)
    row = db_session.query(AuthSession).one()
    assert row.refresh_token_hash != plaintext
    assert row.refresh_token_hash == auth_service.hash_refresh(plaintext)
    assert len(row.refresh_token_hash) == 64


# ---------------------------------------------------------------- refresh
def test_login_refresh_round_trip(client, make_user):
    make_user("round@emesoft.net", "password12345")
    login = client.post(
        "/auth/login", json={"email": "round@emesoft.net", "password": "password12345"}
    ).json()
    first_refresh = client.cookies.get(REFRESH_COOKIE)

    response = client.post("/auth/refresh", headers=_csrf_headers(client))
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["accessToken"]
    assert body["user"]["email"] == "round@emesoft.net"

    # The refresh token rotated, and the new access token still works.
    assert client.cookies.get(REFRESH_COOKIE) != first_refresh
    me = client.get("/me", headers={"Authorization": f"Bearer {body['accessToken']}"})
    assert me.status_code == 200
    assert me.json()["email"] == "round@emesoft.net"
    # Same session across the round trip — the sid is stable, the token is not.
    assert _sid(login["accessToken"]) == _sid(body["accessToken"])


def test_refresh_requires_the_csrf_header(client, make_user):
    make_user("csrf@emesoft.net", "password12345")
    client.post("/auth/login", json={"email": "csrf@emesoft.net", "password": "password12345"})
    assert client.post("/auth/refresh").status_code == 403
    assert client.post("/auth/refresh", headers={CSRF_HEADER: "wrong"}).status_code == 403


def test_refresh_without_a_cookie_is_401(client):
    assert client.post("/auth/refresh", headers={CSRF_HEADER: "x"}).status_code == 401


def test_a_rotated_refresh_token_cannot_be_replayed(client, make_user):
    make_user("replay@emesoft.net", "password12345")
    client.post("/auth/login", json={"email": "replay@emesoft.net", "password": "password12345"})
    stale = client.cookies.get(REFRESH_COOKIE)
    csrf = client.cookies.get(CSRF_COOKIE)
    assert client.post("/auth/refresh", headers=_csrf_headers(client)).status_code == 200

    client.cookies.set(REFRESH_COOKIE, stale)
    client.cookies.set(CSRF_COOKIE, csrf)
    assert client.post("/auth/refresh", headers={CSRF_HEADER: csrf}).status_code == 401


# ---------------------------------------------------------------- profile
def test_me_endpoints(client, make_user, auth_headers):
    make_user("profile@emesoft.net", "password12345")
    headers = auth_headers("profile@emesoft.net", "password12345")

    contract = client.get("/me", headers=headers).json()
    assert contract == {
        "id": contract["id"],
        "email": "profile@emesoft.net",
        "name": "Test User",
        "firstName": "Test",
        "lastName": "User",
        "role": "member",
    }

    patched = client.patch("/auth/me", json={"firstName": "Duna"}, headers=headers)
    assert patched.status_code == 200
    assert patched.json()["firstName"] == "Duna"
    # Never leaks the hash or the TOTP secret.
    assert "passwordHash" not in patched.text and "totpSecret" not in patched.text


def test_change_password_requires_the_current_one(client, make_user, auth_headers):
    make_user("pw@emesoft.net", "password12345")
    headers = auth_headers("pw@emesoft.net", "password12345")

    bad = client.post(
        "/auth/change-password",
        json={"currentPassword": "wrong", "newPassword": "newpassword1"},
        headers=headers,
    )
    assert bad.status_code == 400

    ok = client.post(
        "/auth/change-password",
        json={"currentPassword": "password12345", "newPassword": "newpassword1"},
        headers=headers,
    )
    assert ok.status_code == 200
    assert (
        client.post(
            "/auth/login", json={"email": "pw@emesoft.net", "password": "newpassword1"}
        ).status_code
        == 200
    )


def test_reset_password_flow_revokes_every_session(client, make_user, auth_headers):
    make_user("reset@emesoft.net", "password12345")
    headers = auth_headers("reset@emesoft.net", "password12345")

    requested = client.post("/auth/request-reset", json={"email": "reset@emesoft.net"})
    token = requested.json()["token"]
    assert token

    done = client.post("/auth/reset", json={"token": token, "password": "brandnewpass1"})
    assert done.status_code == 200
    # The old access token's session is gone.
    assert client.get("/auth/me", headers=headers).status_code == 401
    assert (
        client.post(
            "/auth/login", json={"email": "reset@emesoft.net", "password": "brandnewpass1"}
        ).status_code
        == 200
    )


def test_request_reset_does_not_leak_whether_an_email_exists(client, make_user):
    make_user("known@emesoft.net", "password12345")
    known = client.post("/auth/request-reset", json={"email": "known@emesoft.net"})
    unknown = client.post("/auth/request-reset", json={"email": "nobody@emesoft.net"})
    assert known.status_code == unknown.status_code == 200
    assert known.json()["ok"] is unknown.json()["ok"] is True


def test_reset_token_cannot_be_used_as_an_access_token(client, make_user):
    make_user("mix@emesoft.net", "password12345")
    token = client.post("/auth/request-reset", json={"email": "mix@emesoft.net"}).json()["token"]
    assert client.get("/me", headers={"Authorization": f"Bearer {token}"}).status_code == 401


def _sid(token: str) -> str:
    return jwt.decode(token, options={"verify_signature": False})["sid"]
