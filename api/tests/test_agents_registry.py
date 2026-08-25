"""``GET /agents`` — the launch registry, and the readiness logic behind it.

The distinction under test is **registered** vs **handoffReady**: an agent can be
registered (a URL is set, so the hub mints it tokens) while single sign-on still
cannot work, because ``EMEHUB_COOKIE_DOMAIN`` is unset or does not cover the
agent's origin. Conflating the two would have the UI offer a launch that silently
fails, which is the thing ADR 0008 wants avoided.
"""

from __future__ import annotations

import pytest

from app.config import AUDIENCE_DAGENT, AUDIENCE_QAGENT, Settings


def _by_id(body: dict) -> dict:
    return {a["id"]: a for a in body["agents"]}


def _settings(**kwargs) -> Settings:
    return Settings(jwt_secret="a-secret", encryption_key="another-secret", **kwargs)


@pytest.fixture
def hub_headers(make_user, auth_headers):
    """Ready-made hub-audience header for a fresh admin."""
    make_user("registry@emesoft.net", "password12345", role="admin")
    return auth_headers("registry@emesoft.net", "password12345")


# ------------------------------------------------------------------ the endpoint
def test_lists_both_agents(client, hub_headers):
    response = client.get("/agents", headers=hub_headers)
    assert response.status_code == 200, response.text
    agents = _by_id(response.json())
    assert set(agents) == {AUDIENCE_QAGENT, AUDIENCE_DAGENT}
    assert agents[AUDIENCE_QAGENT]["name"] == "Q-Agent"
    assert agents[AUDIENCE_QAGENT]["key"] == "q"
    assert agents[AUDIENCE_DAGENT]["key"] == "d"


def test_requires_authentication(client):
    assert client.get("/agents").status_code == 401


def test_an_agent_token_is_refused(client, login, make_user):
    """The registry is hub-only — an agent must not enumerate its siblings."""
    make_user("sibling@emesoft.net", "password12345")
    tokens = login("sibling@emesoft.net", "password12345")["tokens"]
    response = client.get(
        "/agents", headers={"Authorization": f"Bearer {tokens[AUDIENCE_QAGENT]}"}
    )
    assert response.status_code in (401, 403)


def test_an_unregistered_agent_reports_no_url(client, hub_headers, monkeypatch):
    from app import config as config_module

    monkeypatch.setattr(config_module.settings, "agent_dagent_url", "")
    dagent = _by_id(client.get("/agents", headers=hub_headers).json())[AUDIENCE_DAGENT]

    assert dagent["registered"] is False
    assert dagent["handoffReady"] is False
    assert dagent["reason"] == "no_url"
    assert dagent["url"] is None


def test_registered_but_no_cookie_domain_is_not_handoff_ready(client, hub_headers, monkeypatch):
    """The default localhost stack: tokens can be minted, SSO cannot work."""
    from app import config as config_module

    monkeypatch.setattr(config_module.settings, "agent_qagent_url", "http://localhost:5174")
    monkeypatch.setattr(config_module.settings, "cookie_domain", "")
    qagent = _by_id(client.get("/agents", headers=hub_headers).json())[AUDIENCE_QAGENT]

    assert qagent["registered"] is True
    assert qagent["handoffReady"] is False
    assert qagent["reason"] == "no_cookie_domain"


def test_a_matching_domain_is_handoff_ready(client, hub_headers, monkeypatch):
    from app import config as config_module

    monkeypatch.setattr(
        config_module.settings, "agent_qagent_url", "https://qagent.chuongnd.click"
    )
    monkeypatch.setattr(config_module.settings, "cookie_domain", ".chuongnd.click")
    qagent = _by_id(client.get("/agents", headers=hub_headers).json())[AUDIENCE_QAGENT]

    assert qagent["registered"] is True
    assert qagent["handoffReady"] is True
    assert qagent["reason"] is None


# ------------------------------------------------------------------ readiness rules
@pytest.mark.parametrize(
    ("cookie_domain", "url", "ready", "reason"),
    [
        # The deployment this was built for, with and without the leading dot.
        (".chuongnd.click", "https://qagent.chuongnd.click", True, None),
        ("chuongnd.click", "https://qagent.chuongnd.click", True, None),
        # The cookie domain itself is a valid host for an agent.
        (".chuongnd.click", "https://chuongnd.click", True, None),
        # A different registrable domain cannot receive the cookie.
        (".chuongnd.click", "https://qagent.example.com", False, "domain_mismatch"),
        # Nor can a lookalike that merely ends in the same characters.
        (".chuongnd.click", "https://evilchuongnd.click", False, "domain_mismatch"),
        # localhost is honest about it: with a cookie domain set, SSO can't work.
        (".chuongnd.click", "http://localhost:5174", False, "domain_mismatch"),
        # Missing pieces.
        ("", "https://qagent.chuongnd.click", False, "no_cookie_domain"),
        (".chuongnd.click", "", False, "no_url"),
        ("", "", False, "no_url"),
        # A same-origin path: the agent is mounted behind the hub's own reverse
        # proxy, so the cookie is already on the origin. Ready with NO cookie
        # domain at all — the case a hostname-only rule gets exactly backwards,
        # because `urlsplit("///qagent").hostname` is None and the suffix test
        # then reports `domain_mismatch` for the *strongest* hand-off there is.
        ("", "/qagent", True, None),
        (".chuongnd.click", "/qagent", True, None),
        ("", "/qagent/", True, None),
        # Protocol-relative is an ORIGIN with the scheme left off, not a path.
        # Treating it as same-origin would hand "always ready" to any host.
        ("", "//evil.example.com/qagent", False, "no_cookie_domain"),
        (".chuongnd.click", "//evil.example.com/qagent", False, "domain_mismatch"),
    ],
)
def test_handoff_readiness(cookie_domain, url, ready, reason):
    settings = _settings(cookie_domain=cookie_domain, agent_qagent_url=url)
    assert settings.handoff_ready(AUDIENCE_QAGENT) is ready
    assert settings.handoff_blocker(AUDIENCE_QAGENT) == reason


def test_a_lookalike_domain_is_not_a_suffix_match():
    """`evilchuongnd.click` must not satisfy a `.chuongnd.click` cookie domain.

    A naive ``endswith(domain)`` would accept it, which would put the hand-off's
    trust boundary in the wrong place.
    """
    settings = _settings(
        cookie_domain=".chuongnd.click", agent_qagent_url="https://evilchuongnd.click"
    )
    assert settings.handoff_ready(AUDIENCE_QAGENT) is False


def test_readiness_does_not_depend_on_the_scheme_being_https():
    """Deliberate: the domain rule is about cookie scope, not transport.

    `EMEHUB_COOKIE_SECURE` governs transport, and it is a separate setting.
    """
    settings = _settings(
        cookie_domain=".chuongnd.click", agent_qagent_url="http://qagent.chuongnd.click"
    )
    assert settings.handoff_ready(AUDIENCE_QAGENT) is True


# --------------------------------------------------- availability toggle (#186)
def test_an_agent_is_open_until_somebody_closes_it(client, hub_headers):
    """#186: absent means available.

    Nothing is seeded, so a fresh install must read as open. A table that had to
    be populated before the suite worked would be a new way to come up broken.
    """
    agents = _by_id(client.get("/agents", headers=hub_headers).json())
    assert agents[AUDIENCE_QAGENT]["enabled"] is True
    assert agents[AUDIENCE_DAGENT]["enabled"] is True


def test_an_admin_can_close_one_agent_without_touching_the_other(client, hub_headers):
    """#186: the toggle is per agent, and it reaches the registry the cards read."""
    response = client.put(
        f"/agents/{AUDIENCE_QAGENT}/availability", json={"enabled": False}, headers=hub_headers
    )
    assert response.status_code == 200, response.text
    assert response.json() == {"key": AUDIENCE_QAGENT, "enabled": False}

    agents = _by_id(client.get("/agents", headers=hub_headers).json())
    assert agents[AUDIENCE_QAGENT]["enabled"] is False
    assert agents[AUDIENCE_DAGENT]["enabled"] is True, "closing one closed the other"

    # And it is reversible — a coming-soon state that could not be undone would be
    # a deploy-shaped decision again, which is what this replaced.
    client.put(
        f"/agents/{AUDIENCE_QAGENT}/availability", json={"enabled": True}, headers=hub_headers
    )
    agents = _by_id(client.get("/agents", headers=hub_headers).json())
    assert agents[AUDIENCE_QAGENT]["enabled"] is True


def test_a_member_cannot_change_availability(client, make_user, auth_headers):
    """#186: turning a product off is an admin decision."""
    make_user("member@emesoft.net", "password12345", role="member")
    headers = auth_headers("member@emesoft.net", "password12345")

    response = client.put(
        f"/agents/{AUDIENCE_QAGENT}/availability", json={"enabled": False}, headers=headers
    )
    assert response.status_code == 403, response.text


def test_the_edge_can_ask_without_a_session(client, hub_headers):
    """#186: the gate has to work for the very people it exists for.

    Someone following a link to a product that is not open yet has no hub session.
    Requiring one would mean the edge could not run the check for a stranger — the
    only case that matters — so this read is deliberately unauthenticated. It
    reveals nothing: the answer is what the coming-soon page says out loud.
    """
    client.put(
        f"/agents/{AUDIENCE_QAGENT}/availability", json={"enabled": False}, headers=hub_headers
    )

    # 403 is the answer, not an error: nginx `auth_request` reads status codes and
    # cannot parse a body, so a 200 saying "enabled: false" would be a gate that
    # always opens. The body is still there so a human with curl sees why.
    closed = client.get(f"/agents/{AUDIENCE_QAGENT}/open")
    assert closed.status_code == 403, closed.text
    assert closed.json() == {"key": AUDIENCE_QAGENT, "enabled": False}

    client.put(
        f"/agents/{AUDIENCE_QAGENT}/availability", json={"enabled": True}, headers=hub_headers
    )
    opened = client.get(f"/agents/{AUDIENCE_QAGENT}/open")
    assert opened.status_code == 200, opened.text
    assert opened.json() == {"key": AUDIENCE_QAGENT, "enabled": True}


def test_an_unknown_agent_reads_as_open_but_cannot_be_written(client, hub_headers):
    """#186: be permissive where being wrong causes an outage, strict where it doesn't.

    The read gates access, so a typo in a route must not take a product down. The
    write is where a bad name should be refused, because there it is cheap and
    immediately visible.
    """
    # Not allowlisted, so the guard refuses it before routing — an unknown name
    # cannot even probe for existence, which is the stricter and better answer.
    assert client.get("/agents/nosuchagent/open").status_code == 401

    response = client.put(
        "/agents/nosuchagent/availability", json={"enabled": False}, headers=hub_headers
    )
    assert response.status_code == 404, response.text
