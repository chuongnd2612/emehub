"""Provider read-through for one ticket: comments and test cases.

Driven through the injected adapter seam (``ticket_provider.use_adapter_resolver``),
so these verify the endpoints' behaviour — scoping, capability reporting, failure
mapping — without any provider connection existing.

The properties worth protecting here are mostly *negative*, because the bug this
slice exists to avoid is answering ``200 []`` to three different questions:
"there are none", "this provider can't", and "the call failed".
"""

from __future__ import annotations

import pytest

from app.config import AUDIENCE_DAGENT, AUDIENCE_QAGENT
from app.services import ticket_provider


class FakeAdapter:
    """A :class:`ticket_provider.TicketAdapter`. Records what it was asked."""

    def __init__(
        self,
        *,
        comments=None,
        test_cases=None,
        supports_comments=True,
        supports_test_cases=True,
        test_cases_project_wide=False,
        raises: Exception | None = None,
    ) -> None:
        self.supports_comments = supports_comments
        self.supports_test_cases = supports_test_cases
        self.test_cases_project_wide = test_cases_project_wide
        self._comments = comments if comments is not None else []
        self._test_cases = test_cases if test_cases is not None else []
        self._raises = raises
        self.calls: list[tuple[str, str | None]] = []

    def fetch_comments(self, ticket_external_id):
        self.calls.append(("fetch_comments", ticket_external_id))
        if self._raises:
            raise self._raises
        return self._comments

    def list_test_cases(self, ticket_external_id=None):
        self.calls.append(("list_test_cases", ticket_external_id))
        if self._raises:
            raise self._raises
        return self._test_cases


def resolver_for(adapter):
    def _resolve(db, ticket):
        return adapter

    return _resolve


def failing_resolver(exc: Exception):
    def _resolve(db, ticket):
        raise exc

    return _resolve


@pytest.fixture
def make_ticket(db_session):
    from app.models.ticket import Ticket

    def _make(external_id: str, *, owner=None, **fields):
        ticket = Ticket(
            external_id=external_id,
            provider_kind=fields.pop("provider_kind", "ado"),
            owner_id=(owner.id if owner is not None else None),
            title=fields.pop("title", f"Work item {external_id}"),
            **fields,
        )
        db_session.add(ticket)
        db_session.commit()
        db_session.refresh(ticket)
        return ticket

    return _make


@pytest.fixture
def member(client, make_user, auth_headers):
    user = make_user("provider-read@emesoft.net", "password12345")
    return user, auth_headers("provider-read@emesoft.net", "password12345")


COMMENTS = [
    {"who": "duna", "when": "2026-08-01T09:00:00Z", "text": "Repro'd on staging."},
    {"who": "linh", "when": "2026-08-01T10:30:00Z", "text": "Fixed in 4f2a1c."},
]
CASES = [
    {"external_id": "9001", "title": "Import a valid file", "state": "Design"},
    {"external_id": "9002", "title": "Reject a malformed row", "state": "Ready"},
]


# ---------------------------------------------------------------- the seam
def test_the_fake_satisfies_the_declared_protocol():
    """If this fails, the fake and the real adapter have drifted apart."""
    assert isinstance(FakeAdapter(), ticket_provider.TicketAdapter)


def test_the_real_adapters_satisfy_the_protocol():
    """The protocol must be a strict subset of what the adapters actually offer."""
    from app.services.adapters.azure_devops import AzureDevOpsAdapter
    from app.services.adapters.github import GitHubAdapter
    from app.services.adapters.jira import JiraAdapter

    for cls in (AzureDevOpsAdapter, GitHubAdapter, JiraAdapter):
        adapter = cls({"orgUrl": "https://dev.azure.com/x/y", "org": "o", "repo": "r"}, {"pat": "p"})
        assert isinstance(adapter, ticket_provider.TicketAdapter), cls.__name__


def test_the_resolver_is_restored_on_exit():
    with ticket_provider.use_adapter_resolver(resolver_for(FakeAdapter())):
        pass
    assert ticket_provider._resolver is ticket_provider._resolve_from_connections


# ---------------------------------------------------------------- auth posture
def test_provider_reads_require_authentication(client):
    assert client.get("/tickets/SUR-1/comments").status_code == 401
    assert client.get("/tickets/SUR-1/test-cases").status_code == 401


def test_an_agent_token_may_read_through_to_the_provider(client, make_user, login, make_ticket):
    """CONTRACT posture — this is the whole point: the agent holds no PAT."""
    user = make_user("agent-through@emesoft.net", "password12345")
    make_ticket("SUR-7", owner=user)
    tokens = login("agent-through@emesoft.net", "password12345")["tokens"]
    adapter = FakeAdapter(comments=COMMENTS, test_cases=CASES)

    with ticket_provider.use_adapter_resolver(resolver_for(adapter)):
        for audience in (AUDIENCE_QAGENT, AUDIENCE_DAGENT):
            headers = {"Authorization": f"Bearer {tokens[audience]}"}
            comments = client.get("/tickets/SUR-7/comments", headers=headers)
            assert comments.status_code == 200, comments.text
            assert [c["who"] for c in comments.json()["items"]] == ["duna", "linh"]
            cases = client.get("/tickets/SUR-7/test-cases", headers=headers)
            assert cases.status_code == 200, cases.text
            assert [c["externalId"] for c in cases.json()["items"]] == ["9001", "9002"]


def test_an_unregistered_audience_is_still_refused(client, make_user, login, monkeypatch):
    import app.config as config_module

    make_user("dereg-p@emesoft.net", "password12345")
    dagent = login("dereg-p@emesoft.net", "password12345")["tokens"][AUDIENCE_DAGENT]
    monkeypatch.setattr(config_module.settings, "agent_dagent_url", "")
    response = client.get(
        "/tickets/SUR-1/comments", headers={"Authorization": f"Bearer {dagent}"}
    )
    assert response.status_code == 401


# ---------------------------------------------------------------- happy path
def test_comments_come_back_in_the_stored_shape(client, member, make_ticket):
    """Same keys as the ``comments`` snapshot on GET /tickets/{id}, on purpose."""
    user, headers = member
    make_ticket("SUR-10", owner=user)
    adapter = FakeAdapter(comments=COMMENTS)

    with ticket_provider.use_adapter_resolver(resolver_for(adapter)):
        body = client.get("/tickets/SUR-10/comments", headers=headers).json()

    assert body["supported"] is True
    assert body["items"][0] == {
        "who": "duna",
        "when": "2026-08-01T09:00:00Z",
        "text": "Repro'd on staging.",
    }
    assert adapter.calls == [("fetch_comments", "SUR-10")]


def test_the_ticket_id_is_passed_through_to_the_adapter(client, member, make_ticket):
    user, headers = member
    make_ticket("SUR-11", owner=user)
    adapter = FakeAdapter(test_cases=CASES)

    with ticket_provider.use_adapter_resolver(resolver_for(adapter)):
        client.get("/tickets/SUR-11/test-cases", headers=headers)

    assert adapter.calls == [("list_test_cases", "SUR-11")]


def test_a_genuinely_empty_result_is_supported_and_empty(client, member, make_ticket):
    """The third of the three states: supported, reached, nothing there."""
    user, headers = member
    make_ticket("SUR-12", owner=user)

    with ticket_provider.use_adapter_resolver(resolver_for(FakeAdapter(comments=[]))):
        body = client.get("/tickets/SUR-12/comments", headers=headers).json()

    assert body == {"items": [], "supported": True}


# ------------------------------------------------- unsupported vs empty vs failed
def test_an_unsupported_read_says_so_rather_than_returning_nothing(
    client, member, make_ticket
):
    """Jira has no test cases. "Not supported" must not read as "there are none"."""
    user, headers = member
    make_ticket("JIRA-1", owner=user, provider_kind="jira")
    adapter = FakeAdapter(supports_test_cases=False, supports_comments=False)

    with ticket_provider.use_adapter_resolver(resolver_for(adapter)):
        cases = client.get("/tickets/JIRA-1/test-cases", headers=headers).json()
        comments = client.get("/tickets/JIRA-1/comments", headers=headers).json()

    assert cases["supported"] is False and cases["items"] == []
    assert comments["supported"] is False and comments["items"] == []
    # And the provider was never called for a capability it does not have.
    assert adapter.calls == []


def test_a_provider_failure_is_502_and_never_an_empty_list(client, member, make_ticket):
    """INTEGRATION.md §5: a failed read must not be mistakable for an empty one."""
    user, headers = member
    make_ticket("SUR-13", owner=user)
    adapter = FakeAdapter(raises=RuntimeError("Azure DevOps rejected the comment read"))

    with ticket_provider.use_adapter_resolver(resolver_for(adapter)):
        response = client.get("/tickets/SUR-13/comments", headers=headers)

    assert response.status_code == 502
    assert "SUR-13" in response.json()["detail"]


def test_a_missing_work_item_connection_is_404_not_502(client, member, make_ticket):
    """A routing gap is not a provider failure."""
    user, headers = member
    make_ticket("SUR-14", owner=user)
    exc = ticket_provider.NoWorkItemConnection("No work-item connection is configured for 'ado'")

    with ticket_provider.use_adapter_resolver(failing_resolver(exc)):
        response = client.get("/tickets/SUR-14/comments", headers=headers)

    assert response.status_code == 404


def test_an_undecryptable_pat_is_502(client, member, make_ticket):
    """Never passed on as an empty credential, which would read as "no PAT"."""
    user, headers = member
    make_ticket("SUR-15", owner=user)
    exc = ticket_provider.ProviderUnavailable("cannot be decrypted with the current key")

    with ticket_provider.use_adapter_resolver(failing_resolver(exc)):
        response = client.get("/tickets/SUR-15/test-cases", headers=headers)

    assert response.status_code == 502


def test_a_missing_adapter_layer_is_503(client, member, make_ticket):
    user, headers = member
    make_ticket("SUR-16", owner=user)
    exc = ticket_provider.AdapterLayerMissing("not available in this deployment")

    with ticket_provider.use_adapter_resolver(failing_resolver(exc)):
        response = client.get("/tickets/SUR-16/comments", headers=headers)

    assert response.status_code == 503


def test_project_wide_test_cases_are_flagged(client, member, make_ticket):
    """ADO answers project-wide; a caller assuming scoping would over-count."""
    user, headers = member
    make_ticket("SUR-17", owner=user)
    scoped = FakeAdapter(test_cases=CASES, test_cases_project_wide=False)
    wide = FakeAdapter(test_cases=CASES, test_cases_project_wide=True)

    with ticket_provider.use_adapter_resolver(resolver_for(scoped)):
        assert client.get("/tickets/SUR-17/test-cases", headers=headers).json()[
            "projectWide"
        ] is False
    with ticket_provider.use_adapter_resolver(resolver_for(wide)):
        assert client.get("/tickets/SUR-17/test-cases", headers=headers).json()[
            "projectWide"
        ] is True


# ---------------------------------------------------------------- scoping
def test_a_missing_ticket_is_404_before_any_provider_call(client, member):
    _, headers = member
    adapter = FakeAdapter(comments=COMMENTS)

    with ticket_provider.use_adapter_resolver(resolver_for(adapter)):
        assert client.get("/tickets/NOPE-1/comments", headers=headers).status_code == 404
        assert client.get("/tickets/NOPE-1/test-cases", headers=headers).status_code == 404

    assert adapter.calls == []


def test_another_members_ticket_is_404_not_403(
    client, member, make_user, auth_headers, make_ticket
):
    """A 403 would confirm the ticket exists. Same rule as every other read."""
    other = make_user("someone-else@emesoft.net", "password12345")
    make_ticket("SECRET-1", owner=other)
    _, headers = member
    adapter = FakeAdapter(comments=COMMENTS)

    with ticket_provider.use_adapter_resolver(resolver_for(adapter)):
        assert client.get("/tickets/SECRET-1/comments", headers=headers).status_code == 404
        assert client.get("/tickets/SECRET-1/test-cases", headers=headers).status_code == 404

    # The decisive part: the provider was never reached on another member's behalf.
    assert adapter.calls == []


def test_a_shared_ticket_is_readable(client, member, make_ticket):
    _, headers = member
    make_ticket("SHARED-1", owner=None)

    with ticket_provider.use_adapter_resolver(resolver_for(FakeAdapter(comments=COMMENTS))):
        assert client.get("/tickets/SHARED-1/comments", headers=headers).status_code == 200


def test_provider_kind_disambiguates(client, member, make_ticket):
    user, headers = member
    make_ticket("DUP-1", owner=user, provider_kind="ado")
    make_ticket("DUP-1", owner=user, provider_kind="jira")

    with ticket_provider.use_adapter_resolver(resolver_for(FakeAdapter(comments=COMMENTS))):
        ok = client.get("/tickets/DUP-1/comments?providerKind=jira", headers=headers)
        missing = client.get("/tickets/DUP-1/comments?providerKind=github", headers=headers)

    assert ok.status_code == 200
    assert missing.status_code == 404
