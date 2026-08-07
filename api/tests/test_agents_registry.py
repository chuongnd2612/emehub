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
