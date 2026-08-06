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
    cookies = response.headers.get_list("set-cookie")
    assert cookies, "no cookies were set at all"
    assert any(REFRESH_COOKIE in c for c in cookies)
    assert not any("domain=" in c.lower() for c in cookies), cookies


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
    cookies = response.headers.get_list("set-cookie")
    for name in (REFRESH_COOKIE, CSRF_COOKIE):
        cookie = next(c for c in cookies if name in c)
        assert "chuongnd.click" in cookie.lower(), cookie


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
