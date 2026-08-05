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
        comment_id: str = "c-1",
        created=None,
        fail_titles: tuple[str, ...] = (),
    ) -> None:
        self.supports_comments = supports_comments
        self.supports_test_cases = supports_test_cases
        self.test_cases_project_wide = test_cases_project_wide
        self._comments = comments if comments is not None else []
        self._test_cases = test_cases if test_cases is not None else []
        self._raises = raises
        self._comment_id = comment_id
        self._created = created
        #: Titles this fake rejects, so a batch can be partially successful.
        self._fail_titles = fail_titles
        self.calls: list[tuple] = []

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

    def publish_comment(self, ticket_external_id, body, *, attachments=None):
        self.calls.append(("publish_comment", ticket_external_id, body, attachments))
        if self._raises:
            raise self._raises
        return self._comment_id

    def update_status(self, ticket_external_id, target_status):
        self.calls.append(("update_status", ticket_external_id, target_status))
        if self._raises:
            raise self._raises

    def create_test_case(
        self,
        ticket_external_id,
        *,
        title,
        precondition="",
        steps=None,
        priority="Medium",
        link=True,
    ):
        self.calls.append(("create_test_case", ticket_external_id, title, priority, link))
        if self._raises:
            raise self._raises
        if title in self._fail_titles:
            raise RuntimeError(f"Provider rejected '{title}'")
        return self._created or {
            "external_id": f"tc-{title}",
            "url": f"https://provider/{title}",
            "status": "Design",
            "linked": link,
        }


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


# ================================================================ writes
def test_provider_writes_require_authentication(client):
    assert client.post("/tickets/SUR-1/comments", json={"body": "hi"}).status_code == 401
    assert client.post("/tickets/SUR-1/state", json={"targetStatus": "Done"}).status_code == 401
    assert (
        client.post("/tickets/SUR-1/test-cases", json={"cases": [{"title": "t"}]}).status_code
        == 401
    )


def test_an_agent_token_may_write_through_to_the_provider(
    client, make_user, login, make_ticket
):
    """The point of the slice: the agent causes a provider write holding no PAT."""
    user = make_user("agent-write@emesoft.net", "password12345")
    make_ticket("SUR-20", owner=user)
    qagent = login("agent-write@emesoft.net", "password12345")["tokens"][AUDIENCE_QAGENT]
    headers = {"Authorization": f"Bearer {qagent}"}
    adapter = FakeAdapter()

    with ticket_provider.use_adapter_resolver(resolver_for(adapter)):
        posted = client.post("/tickets/SUR-20/comments", json={"body": "42 passed"}, headers=headers)
        moved = client.post(
            "/tickets/SUR-20/state", json={"targetStatus": "Done"}, headers=headers
        )
        made = client.post(
            "/tickets/SUR-20/test-cases",
            json={"cases": [{"title": "Imports a valid file"}]},
            headers=headers,
        )

    assert posted.status_code == 201, posted.text
    assert posted.json()["externalCommentId"] == "c-1"
    assert moved.status_code == 200, moved.text
    assert made.status_code == 201, made.text


# ---------------------------------------------------------------- comments
def test_a_published_comment_is_mirrored_into_the_stored_snapshot(
    client, member, make_ticket, db_session
):
    """The hub must not need a re-sync to know about a comment it posted itself."""
    user, headers = member
    ticket = make_ticket("SUR-21", owner=user, comments=[])
    adapter = FakeAdapter(comment_id="99")

    with ticket_provider.use_adapter_resolver(resolver_for(adapter)):
        response = client.post(
            "/tickets/SUR-21/comments",
            json={"body": "Run finished: 42 passed, 1 failed"},
            headers=headers,
        )
        detail = client.get("/tickets/SUR-21", headers=headers).json()

    assert response.json()["externalCommentId"] == "99"
    assert adapter.calls == [
        ("publish_comment", "SUR-21", "Run finished: 42 passed, 1 failed", None)
    ]
    # Mirrored, in the same {who, when, text} shape sync produces.
    assert len(detail["comments"]) == 1
    assert detail["comments"][0]["text"] == "Run finished: 42 passed, 1 failed"
    assert detail["comments"][0]["who"] == user.email
    assert detail["comments"][0]["when"]
    db_session.refresh(ticket)


def test_attachments_are_passed_through(client, member, make_ticket):
    user, headers = member
    make_ticket("SUR-22", owner=user)
    adapter = FakeAdapter()

    with ticket_provider.use_adapter_resolver(resolver_for(adapter)):
        client.post(
            "/tickets/SUR-22/comments",
            json={"body": "see log", "attachments": ["run.log"]},
            headers=headers,
        )

    assert adapter.calls[0][3] == ["run.log"]


def test_an_empty_comment_body_is_rejected_before_the_provider(client, member, make_ticket):
    user, headers = member
    make_ticket("SUR-23", owner=user)
    adapter = FakeAdapter()

    with ticket_provider.use_adapter_resolver(resolver_for(adapter)):
        response = client.post("/tickets/SUR-23/comments", json={"body": ""}, headers=headers)

    assert response.status_code == 422
    assert adapter.calls == []


def test_a_failed_publish_is_502_and_leaves_the_snapshot_untouched(
    client, member, make_ticket
):
    user, headers = member
    make_ticket("SUR-24", owner=user, comments=[])
    adapter = FakeAdapter(raises=RuntimeError("Azure DevOps rejected the comment"))

    with ticket_provider.use_adapter_resolver(resolver_for(adapter)):
        response = client.post("/tickets/SUR-24/comments", json={"body": "x"}, headers=headers)
        detail = client.get("/tickets/SUR-24", headers=headers).json()

    assert response.status_code == 502
    # The provider's own reason survives — it is the only actionable part.
    assert "rejected the comment" in response.json()["detail"]
    assert detail["comments"] == []


# ---------------------------------------------------------------- transitions
def test_a_transition_updates_the_local_row(client, member, make_ticket):
    user, headers = member
    make_ticket("SUR-25", owner=user, status="Ready for QA")
    adapter = FakeAdapter()

    with ticket_provider.use_adapter_resolver(resolver_for(adapter)):
        response = client.post(
            "/tickets/SUR-25/state", json={"targetStatus": "Done"}, headers=headers
        )

    assert response.status_code == 200
    assert response.json()["status"] == "Done"
    assert adapter.calls == [("update_status", "SUR-25", "Done")]


def test_a_rejected_transition_does_not_touch_the_local_row(client, member, make_ticket):
    """The hub must never record a status the provider never reached."""
    user, headers = member
    make_ticket("SUR-26", owner=user, status="Ready for QA")
    adapter = FakeAdapter(raises=RuntimeError("No state matching 'Shipped'"))

    with ticket_provider.use_adapter_resolver(resolver_for(adapter)):
        response = client.post(
            "/tickets/SUR-26/state", json={"targetStatus": "Shipped"}, headers=headers
        )
        detail = client.get("/tickets/SUR-26", headers=headers).json()

    assert response.status_code == 502
    assert "No state matching 'Shipped'" in response.json()["detail"]
    assert detail["status"] == "Ready for QA"


def test_the_base_adapter_refuses_to_transition_rather_than_no_opping():
    """A silent no-op would report success for a transition that never happened."""
    from app.services.adapters.base import ProviderAdapter, ProviderError

    class Bare(ProviderAdapter):
        kind = "bare"

        def test_connection(self):
            return {}

        def fetch_tickets(self, **kwargs):
            return []

        def list_projects(self):
            return []

        def publish_comment(self, ticket_external_id, body, *, attachments=None):
            return ""

    with pytest.raises(ProviderError, match="not supported"):
        Bare({}, {}).update_status("1", "Done")


# ---------------------------------------------------------------- test cases
def test_test_cases_are_created_in_one_pass_with_per_case_results(
    client, member, make_ticket
):
    user, headers = member
    make_ticket("SUR-27", owner=user)
    adapter = FakeAdapter()

    with ticket_provider.use_adapter_resolver(resolver_for(adapter)):
        response = client.post(
            "/tickets/SUR-27/test-cases",
            json={
                "cases": [
                    {"title": "Imports a valid file", "priority": "High"},
                    {"title": "Rejects a malformed row", "steps": [{"a": "upload", "e": "error"}]},
                ]
            },
            headers=headers,
        )

    body = response.json()
    assert response.status_code == 201
    assert body["succeeded"] == 2 and body["failed"] == 0
    assert [c["externalId"] for c in body["created"]] == [
        "tc-Imports a valid file",
        "tc-Rejects a malformed row",
    ]
    assert all(c["linked"] for c in body["created"])
    # One pass: the connection is resolved once, not once per case.
    assert [c[0] for c in adapter.calls] == ["create_test_case", "create_test_case"]


def test_a_partially_failing_batch_keeps_the_cases_that_landed(client, member, make_ticket):
    """Partial success is normal, not an edge case — one rejection must not
    discard the cases created before it."""
    user, headers = member
    make_ticket("SUR-28", owner=user)
    adapter = FakeAdapter(fail_titles=("Rejects a malformed row",))

    with ticket_provider.use_adapter_resolver(resolver_for(adapter)):
        response = client.post(
            "/tickets/SUR-28/test-cases",
            json={
                "cases": [
                    {"title": "Imports a valid file"},
                    {"title": "Rejects a malformed row"},
                    {"title": "Handles an empty file"},
                ]
            },
            headers=headers,
        )

    body = response.json()
    assert response.status_code == 201
    assert body["succeeded"] == 2 and body["failed"] == 1
    created = {c["title"]: c for c in body["created"]}
    assert created["Imports a valid file"]["externalId"] == "tc-Imports a valid file"
    assert created["Handles an empty file"]["externalId"] == "tc-Handles an empty file"
    assert created["Rejects a malformed row"]["error"] == "Provider rejected 'Rejects a malformed row'"
    assert created["Rejects a malformed row"]["externalId"] == ""


def test_link_false_is_honoured(client, member, make_ticket):
    user, headers = member
    make_ticket("SUR-29", owner=user)
    adapter = FakeAdapter()

    with ticket_provider.use_adapter_resolver(resolver_for(adapter)):
        body = client.post(
            "/tickets/SUR-29/test-cases",
            json={"cases": [{"title": "Standalone"}], "link": False},
            headers=headers,
        ).json()

    assert adapter.calls[0][4] is False
    assert body["created"][0]["linked"] is False


def test_an_empty_case_list_is_rejected(client, member, make_ticket):
    user, headers = member
    make_ticket("SUR-30", owner=user)
    adapter = FakeAdapter()

    with ticket_provider.use_adapter_resolver(resolver_for(adapter)):
        response = client.post("/tickets/SUR-30/test-cases", json={"cases": []}, headers=headers)

    assert response.status_code == 422
    assert adapter.calls == []


def test_a_wholly_unroutable_batch_is_404_not_a_partial_success(client, member, make_ticket):
    """Nothing partial about it when no case could be attempted."""
    user, headers = member
    make_ticket("SUR-31", owner=user)
    exc = ticket_provider.NoWorkItemConnection("No work-item connection is configured for 'ado'")

    with ticket_provider.use_adapter_resolver(failing_resolver(exc)):
        response = client.post(
            "/tickets/SUR-31/test-cases",
            json={"cases": [{"title": "Anything"}]},
            headers=headers,
        )

    assert response.status_code == 404


# ---------------------------------------------------------------- write scoping
def test_writes_cannot_reach_another_members_ticket(
    client, member, make_user, make_ticket
):
    """404, and — decisively — the provider is never called on their behalf."""
    other = make_user("victim@emesoft.net", "password12345")
    make_ticket("SECRET-9", owner=other, status="Ready for QA")
    _, headers = member
    adapter = FakeAdapter()

    with ticket_provider.use_adapter_resolver(resolver_for(adapter)):
        assert (
            client.post("/tickets/SECRET-9/comments", json={"body": "x"}, headers=headers)
        ).status_code == 404
        assert (
            client.post("/tickets/SECRET-9/state", json={"targetStatus": "Done"}, headers=headers)
        ).status_code == 404
        assert (
            client.post(
                "/tickets/SECRET-9/test-cases",
                json={"cases": [{"title": "t"}]},
                headers=headers,
            )
        ).status_code == 404

    assert adapter.calls == []


# ---------------------------------------------------------------- audit
def test_every_write_is_audited_with_the_calling_audience(
    client, make_user, login, make_ticket, db_session
):
    """These are the first agent-caused writes that leave the hub for a third
    party, so the audit row is the only record that it happened."""
    from app.models.audit import AuditLog

    user = make_user("audited@emesoft.net", "password12345")
    make_ticket("SUR-32", owner=user, status="Ready for QA")
    qagent = login("audited@emesoft.net", "password12345")["tokens"][AUDIENCE_QAGENT]
    headers = {"Authorization": f"Bearer {qagent}"}

    with ticket_provider.use_adapter_resolver(resolver_for(FakeAdapter())):
        client.post("/tickets/SUR-32/comments", json={"body": "done"}, headers=headers)
        client.post("/tickets/SUR-32/state", json={"targetStatus": "Done"}, headers=headers)
        client.post(
            "/tickets/SUR-32/test-cases", json={"cases": [{"title": "t"}]}, headers=headers
        )

    events = (
        db_session.query(AuditLog)
        .filter(AuditLog.target == "SUR-32")
        .order_by(AuditLog.id)
        .all()
    )
    assert [e.action for e in events] == [
        "Posted a comment",
        "Transitioned to 'Done'",
        "Created test cases",
    ]
    assert {e.source for e in events} == {AUDIENCE_QAGENT}
    assert {e.status for e in events} == {"success"}


def test_a_failed_write_is_audited_as_an_error(
    client, make_user, login, make_ticket, db_session
):
    from app.models.audit import AuditLog

    user = make_user("audited-fail@emesoft.net", "password12345")
    make_ticket("SUR-33", owner=user)
    qagent = login("audited-fail@emesoft.net", "password12345")["tokens"][AUDIENCE_QAGENT]
    headers = {"Authorization": f"Bearer {qagent}"}
    adapter = FakeAdapter(raises=RuntimeError("provider exploded"))

    with ticket_provider.use_adapter_resolver(resolver_for(adapter)):
        assert (
            client.post("/tickets/SUR-33/comments", json={"body": "x"}, headers=headers)
        ).status_code == 502

    event = db_session.query(AuditLog).filter(AuditLog.target == "SUR-33").one()
    assert event.status == "error"
    assert "provider exploded" in event.meta


def test_a_partial_batch_is_audited_as_a_warning(
    client, make_user, login, make_ticket, db_session
):
    from app.models.audit import AuditLog

    user = make_user("audited-part@emesoft.net", "password12345")
    make_ticket("SUR-34", owner=user)
    qagent = login("audited-part@emesoft.net", "password12345")["tokens"][AUDIENCE_QAGENT]
    headers = {"Authorization": f"Bearer {qagent}"}
    adapter = FakeAdapter(fail_titles=("b",))

    with ticket_provider.use_adapter_resolver(resolver_for(adapter)):
        client.post(
            "/tickets/SUR-34/test-cases",
            json={"cases": [{"title": "a"}, {"title": "b"}]},
            headers=headers,
        )

    event = db_session.query(AuditLog).filter(AuditLog.target == "SUR-34").one()
    assert event.status == "warning"
    assert event.meta == "1 created, 1 failed"
