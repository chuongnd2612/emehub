"""The ``Domain`` attribute on the auth cookies.

`EMEHUB_COOKIE_DOMAIN` is what lets the refresh cookie be shared with an agent on
a sibling subdomain (ADR 0008), and it must keep doing exactly that. But a cookie
whose ``Domain`` is not the request host or a parent of it is rejected by every
browser — so sending it unconditionally left the hub unable to hold a session on
any other host at all. Reached at ``http://localhost:5180`` it set
``Domain=.chuongnd.click``, the browser stored nothing, and every load was a
fresh login.

These pin both halves: the shared domain is still sent to hosts inside it, and
omitted for anything else.
"""

from __future__ import annotations

import pytest

from app.deps_auth import CSRF_COOKIE, REFRESH_COOKIE, cookie_domain_for

PASSWORD = "password12345"


class _Url:
    def __init__(self, hostname: str) -> None:
        self.hostname = hostname


class _Request:
    """Only the one attribute `cookie_domain_for` reads."""

    def __init__(self, hostname: str) -> None:
        self.url = _Url(hostname)


@pytest.fixture
def configured(monkeypatch):
    import app.config as config_module

    monkeypatch.setattr(config_module.settings, "cookie_domain", ".chuongnd.click")
    return ".chuongnd.click"


# ------------------------------------------------------------------ the decision
@pytest.mark.parametrize(
    "host",
    ["hub.chuongnd.click", "qagent.chuongnd.click", "chuongnd.click", "HUB.ChuongND.click"],
)
def test_the_shared_domain_is_sent_to_hosts_inside_it(configured, host):
    """This is the sign-in hand-off's mechanism and must not change."""
    assert cookie_domain_for(_Request(host)) == configured


@pytest.mark.parametrize(
    "host",
    [
        "localhost",
        "127.0.0.1",
        "example.com",
        # The suffix trap: a host that merely ENDS with the domain text but is not
        # inside it. Matching on `endswith` alone would hand our cookie over.
        "notchuongnd.click",
        "evilchuongnd.click",
    ],
)
def test_it_is_omitted_for_hosts_outside_the_domain(configured, host):
    assert cookie_domain_for(_Request(host)) is None


def test_no_configured_domain_means_host_only(monkeypatch):
    import app.config as config_module

    monkeypatch.setattr(config_module.settings, "cookie_domain", "")
    assert cookie_domain_for(_Request("hub.chuongnd.click")) is None


def test_a_missing_request_is_host_only(configured):
    """Defensive: a caller with no request must not leak the shared domain."""
    assert cookie_domain_for(None) is None


# ------------------------------------------------------------------ end to end
def setter_for(response, name: str) -> str:
    """The Set-Cookie header that actually SETS ``name``.

    A response also carries deletions for the other scope (see
    ``_purge_other_scope``), and those are Set-Cookie headers for the same name
    with an empty value — so matching on the name alone picks up the wrong one.
    """
    headers = [c for c in response.headers.get_list("set-cookie") if c.startswith(f"{name}=")]
    setters = [c for c in headers if not c.startswith(f"{name}=;") and 'Max-Age=0' not in c]
    assert len(setters) == 1, f"expected exactly one setter for {name}, got {headers}"
    return setters[0]


def test_login_on_a_foreign_host_sets_a_host_only_cookie(client, make_user, configured):
    """The regression this fixes: the cookie has to be storable by the browser
    that asked for it, or logging in never sticks."""
    make_user("cookie-host@emesoft.net", PASSWORD)
    response = client.post(
        "/auth/login",
        json={"email": "cookie-host@emesoft.net", "password": PASSWORD},
        headers={"Host": "localhost"},
    )
    assert response.status_code == 200, response.text
    cookie = setter_for(response, REFRESH_COOKIE)
    assert "domain=" not in cookie.lower(), cookie


def test_login_on_the_configured_domain_still_shares_the_cookie(
    client, make_user, configured
):
    make_user("cookie-shared@emesoft.net", PASSWORD)
    response = client.post(
        "/auth/login",
        json={"email": "cookie-shared@emesoft.net", "password": PASSWORD},
        headers={"Host": "hub.chuongnd.click"},
    )
    assert response.status_code == 200, response.text
    for name in (REFRESH_COOKIE, CSRF_COOKIE):
        cookie = setter_for(response, name)
        assert "domain=.chuongnd.click" in cookie.lower(), cookie


def test_the_session_survives_a_refresh_on_a_foreign_host(client, make_user, configured):
    """The whole point: log in, then come back with the cookie you were given."""
    make_user("cookie-refresh@emesoft.net", PASSWORD)
    login = client.post(
        "/auth/login",
        json={"email": "cookie-refresh@emesoft.net", "password": PASSWORD},
        headers={"Host": "localhost"},
    )
    assert login.status_code == 200

    # The TestClient's jar holds whatever the response actually set.
    assert client.cookies.get(REFRESH_COOKIE), "the client stored no refresh cookie"
    refreshed = client.post(
        "/auth/refresh",
        headers={
            "Host": "localhost",
            "X-CSRF-Token": client.cookies.get(CSRF_COOKIE) or "",
        },
    )
    assert refreshed.status_code == 200, refreshed.text
    assert refreshed.json()["accessToken"]


def test_setting_one_scope_deletes_the_other(client, make_user, configured):
    """The duplicate-cookie failure, reproduced against the deployment: a stale
    host-only cookie sits beside the domain-wide one, the browser sends both, and
    the server's cookie dict keeps only one. If the stale one wins,
    ``/auth/refresh`` 401s on every load and the session is unrecoverable by hand.

    So setting one scope must delete the other, making it self-heal on the next
    sign-in.
    """
    make_user("cookie-purge@emesoft.net", PASSWORD)
    response = client.post(
        "/auth/login",
        json={"email": "cookie-purge@emesoft.net", "password": PASSWORD},
        headers={"Host": "hub.chuongnd.click"},
    )
    assert response.status_code == 200

    headers = [
        c for c in response.headers.get_list("set-cookie") if c.startswith(f"{REFRESH_COOKIE}=")
    ]
    # One setter carrying the shared domain...
    assert any("domain=.chuongnd.click" in c.lower() and "max-age=0" not in c.lower() for c in headers), headers
    # ...and one expiry for the host-only variant, which carries no Domain.
    expiries = [c for c in headers if "max-age=0" in c.lower()]
    assert expiries, f"nothing purges the other scope: {headers}"
    assert all("domain=" not in c.lower() for c in expiries), expiries
