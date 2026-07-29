"""TOTP enrolment, the MFA login step, and disabling 2FA."""

from __future__ import annotations

import pyotp


def _code(secret: str) -> str:
    return pyotp.TOTP(secret).now()


def test_setup_enable_and_login_with_a_code(client, make_user, auth_headers):
    make_user("mfa@emesoft.net", "password12345")
    headers = auth_headers("mfa@emesoft.net", "password12345")

    setup = client.post("/auth/2fa/setup", headers=headers)
    assert setup.status_code == 200
    secret = setup.json()["secret"]
    assert "otpauth://" in setup.json()["otpauthUri"]
    assert "EmeHub" in setup.json()["otpauthUri"]

    # Not enabled until a code is verified.
    assert client.get("/auth/me", headers=headers).json()["totpEnabled"] is False
    assert client.post("/auth/2fa/enable", json={"code": "000000"}, headers=headers).status_code == 400
    assert client.post("/auth/2fa/enable", json={"code": _code(secret)}, headers=headers).status_code == 200
    assert client.get("/auth/me", headers=headers).json()["totpEnabled"] is True

    # Login now returns a challenge instead of a token.
    challenge = client.post(
        "/auth/login", json={"email": "mfa@emesoft.net", "password": "password12345"}
    ).json()
    assert challenge["mfaRequired"] is True
    assert challenge["accessToken"] is None
    assert challenge["mfaToken"]

    bad = client.post(
        "/auth/login/mfa", json={"mfaToken": challenge["mfaToken"], "code": "000000"}
    )
    assert bad.status_code == 401

    good = client.post(
        "/auth/login/mfa",
        json={"mfaToken": challenge["mfaToken"], "code": _code(secret)},
    )
    assert good.status_code == 200
    assert good.json()["accessToken"]
    assert good.json()["user"]["email"] == "mfa@emesoft.net"


def test_enable_requires_setup_first(client, make_user, auth_headers):
    make_user("nosetup@emesoft.net", "password12345")
    headers = auth_headers("nosetup@emesoft.net", "password12345")
    response = client.post("/auth/2fa/enable", json={"code": "123456"}, headers=headers)
    assert response.status_code == 400


def test_mfa_token_is_not_an_access_token(client, make_user):
    """A mid-login MFA token must not open anything — it lives in its own
    audience namespace so it can never satisfy the access-token decoder."""
    make_user("half@emesoft.net", "password12345")
    # Enable 2FA first, so login returns a challenge instead of a token.
    signed_in = client.post(
        "/auth/login", json={"email": "half@emesoft.net", "password": "password12345"}
    ).json()
    headers = {"Authorization": f"Bearer {signed_in['accessToken']}"}
    secret = client.post("/auth/2fa/setup", headers=headers).json()["secret"]
    client.post("/auth/2fa/enable", json={"code": _code(secret)}, headers=headers)

    challenge = client.post(
        "/auth/login", json={"email": "half@emesoft.net", "password": "password12345"}
    ).json()
    probe = client.get("/me", headers={"Authorization": f"Bearer {challenge['mfaToken']}"})
    assert probe.status_code == 401


def test_disable_with_a_code_or_a_password(client, make_user, auth_headers):
    make_user("off@emesoft.net", "password12345")
    headers = auth_headers("off@emesoft.net", "password12345")
    secret = client.post("/auth/2fa/setup", headers=headers).json()["secret"]
    client.post("/auth/2fa/enable", json={"code": _code(secret)}, headers=headers)

    assert client.post("/auth/2fa/disable", json={}, headers=headers).status_code == 400
    assert (
        client.post(
            "/auth/2fa/disable", json={"password": "password12345"}, headers=headers
        ).status_code
        == 200
    )
    me = client.get("/auth/me", headers=headers).json()
    assert me["totpEnabled"] is False


def test_totp_secret_is_never_returned_outside_setup(client, make_user, auth_headers):
    make_user("secretive@emesoft.net", "password12345")
    headers = auth_headers("secretive@emesoft.net", "password12345")
    secret = client.post("/auth/2fa/setup", headers=headers).json()["secret"]
    client.post("/auth/2fa/enable", json={"code": _code(secret)}, headers=headers)

    assert secret not in client.get("/auth/me", headers=headers).text
