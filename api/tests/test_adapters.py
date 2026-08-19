"""Provider adapters, against recorded provider payloads.

The **tests** mock the HTTP transport; the product never does. Adapters take a
``transport=`` argument that only a test passes (``adapters.base``), so there is
no code path in the running hub that talks to anything but the real API.

Payloads below are trimmed recordings of real responses — enough fields to prove
the normalisation, no more.
"""

from __future__ import annotations

import json

import httpx
import pytest

from pathlib import Path

from app.services.adapters import get_adapter
from app.services.adapters.azure_devops import AzureDevOpsAdapter, parse_org_url
from app.services.adapters.base import REDACTED, ProviderError, scrub
from app.services.adapters.github import GitHubAdapter
from app.services.adapters.jira import JiraAdapter
from app.services.ticket_query import QueryClause, TicketQuery

PAT = "pat-0123456789-abcdef"


def transport(routes: dict[tuple[str, str], object], default_status: int = 404):
    """A ``MockTransport`` dispatching on ``(method, path)``.

    A route value is either a JSON-serialisable body (200) or an
    ``httpx.Response``. Unmatched requests get ``default_status`` so a test that
    forgets a call fails loudly instead of hanging.

    Paths match exactly or by suffix, so a route can be written as the provider
    documents it (``/_apis/projects``) while the client's base URL contributes
    an organisation prefix (``/emesoft/_apis/projects``).
    """
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        match = routes.get((request.method, request.url.path))
        if match is None:
            for (method, path), value in routes.items():
                if method == request.method and request.url.path.endswith(path):
                    match = value
                    break
        if match is None:
            return httpx.Response(default_status, json={"message": "no route"})
        if isinstance(match, httpx.Response):
            return match
        return httpx.Response(200, json=match)

    mock = httpx.MockTransport(handler)
    mock.seen = seen  # type: ignore[attr-defined]
    return mock


# ============================================================ Azure DevOps
ADO_WIQL = {"workItems": [{"id": 4821}]}

ADO_WORK_ITEMS = {
    "value": [
        {
            "id": 4821,
            "fields": {
                "System.Title": "Member cannot reset their password",
                "System.WorkItemType": "Bug",
                "System.State": "Active",
                "System.TeamProject": "Surveyor",
                "System.IterationPath": "Surveyor\\Release 1\\Sprint 3",
                "System.AreaPath": "Surveyor\\Identity",
                "System.Tags": "regression; identity ",
                "System.AssignedTo": {"displayName": "Duna Nguyen"},
                "Microsoft.VSTS.Common.Priority": 1,
                "System.Description": "<p>Reset mail never arrives.</p><p>Blocks sign-in.</p>",
                "Microsoft.VSTS.Common.AcceptanceCriteria": (
                    "<ul><li>Mail is delivered</li><li>Link expires in 30 minutes</li></ul>"
                ),
            },
            "relations": [
                {"rel": "AttachedFile", "url": "https://x/y/trace.har", "attributes": {"name": "trace.har"}},
                {
                    "rel": "ArtifactLink",
                    "url": "vstfs:///Git/PullRequestId/proj-guid%2Frepo-guid%2F317",
                    "attributes": {"name": "Pull Request"},
                },
            ],
        }
    ]
}


def ado_adapter(mock, **config):
    return AzureDevOpsAdapter(
        {"orgUrl": "https://dev.azure.com/emesoft", "project": "Surveyor", **config},
        {"pat": PAT},
        transport=mock,
    )


def test_azure_devops_normalizes_a_recorded_work_item():
    mock = transport(
        {
            ("POST", "/Surveyor/_apis/wit/wiql"): ADO_WIQL,
            ("GET", "/_apis/wit/workitems"): ADO_WORK_ITEMS,
        }
    )
    [ticket] = ado_adapter(mock).fetch_tickets(
        spec=TicketQuery(
            clauses=(
                QueryClause(
                    field="iterationPath",
                    operator="under",
                    values=("Surveyor\\Release 1\\Sprint 3",),
                ),
            )
        )
    )

    assert ticket["external_id"] == "4821"
    assert ticket["provider_kind"] == "azure_devops"
    assert ticket["title"] == "Member cannot reset their password"
    assert ticket["work_item_type"] == "Bug"
    assert ticket["status"] == "Active"
    assert ticket["priority"] == "High"  # ADO priority 1
    assert ticket["assignee"] == "Duna Nguyen"
    assert ticket["sprint"] == "Sprint 3"  # leaf of the iteration path
    assert ticket["area_path"] == "Surveyor\\Identity"
    assert ticket["labels"] == ["regression", "identity"]
    assert ticket["description"] == "Reset mail never arrives.\nBlocks sign-in."
    assert ticket["acceptance_criteria"] == [
        "Mail is delivered",
        "Link expires in 30 minutes",
    ]
    assert ticket["url"] == "https://dev.azure.com/emesoft/Surveyor/_workitems/edit/4821"
    assert ticket["attachments"] == [{"name": "trace.har", "size": ""}]
    assert ticket["linked_prs"][0]["num"] == "317"
    assert ticket["linked_prs"][0]["url"].endswith("/_git/repo-guid/pullrequest/317")
    # No comments unless asked — the N+1 that makes a sprint sync crawl.
    assert ticket["comments"] == []


def test_azure_devops_does_not_retry_a_rejected_query_unscoped():
    """The old sprint retry existed because `mode="sprint"` DERIVED an iteration path
    the caller never saw, so it could be wrong through no fault of theirs. A clause
    query holds only paths the user picked from this project's own metadata — so a
    400 is a real answer, and dropping the condition to "succeed" would return more
    work items than were asked for.
    """
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/wiql"):
            calls.append(json.loads(request.content)["query"])
            return httpx.Response(400, json={"message": "TF51011: unknown iteration"})
        return httpx.Response(200, json=ADO_WORK_ITEMS)

    with pytest.raises(ProviderError, match="rejected the query"):
        ado_adapter(httpx.MockTransport(handler)).fetch_tickets(
            spec=TicketQuery(
                clauses=(
                    QueryClause(
                        field="iterationPath", operator="under", values=("Surveyor\Sprint 99",)
                    ),
                )
            )
        )
    assert len(calls) == 1, "the condition was silently dropped and retried"


def test_azure_devops_resolves_the_state_against_the_work_item_type():
    """Process templates disagree on state names, so "Done" must be mapped onto
    what the type actually has before the PATCH (DAgent's lib/ado.ts)."""
    patched: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if request.method == "GET" and path.endswith("/_apis/wit/workitems/4821"):
            return httpx.Response(
                200,
                json={"fields": {"System.WorkItemType": "Bug", "System.TeamProject": "Surveyor"}},
            )
        if path.endswith("/Surveyor/_apis/wit/workitemtypes/Bug/states"):
            return httpx.Response(
                200,
                json={"value": [{"name": "New"}, {"name": "Active"}, {"name": "Closed"}]},
            )
        if request.method == "PATCH":
            patched.append(json.loads(request.content)[0])
            return httpx.Response(200, json={"id": 4821})
        return httpx.Response(404, json={})

    adapter = ado_adapter(httpx.MockTransport(handler))
    # "Closed" exists verbatim.
    adapter.update_status("4821", "Closed")
    assert patched[-1]["value"] == "Closed"
    # "Code Active" shares a word with "Active" — good enough to transition.
    adapter.update_status("4821", "code active")
    assert patched[-1]["value"] == "Active"
    # Nothing resembles this, so refuse rather than send a PATCH ADO will reject.
    with pytest.raises(ProviderError, match="No Azure DevOps state"):
        adapter.update_status("4821", "Awaiting Legal")


def test_azure_devops_lists_sprints_from_the_classification_tree():
    mock = transport(
        {
            ("GET", "/Surveyor/_apis/wit/classificationnodes/iterations"): {
                "name": "Surveyor",
                "path": "\\Surveyor\\Iteration",
                "children": [
                    {
                        "identifier": "abc",
                        "name": "Sprint 3",
                        "path": "\\Surveyor\\Iteration\\Release 1\\Sprint 3",
                        "attributes": {"startDate": "2026-07-01T00:00:00Z"},
                    }
                ],
            }
        }
    )
    [sprint] = ado_adapter(mock).list_sprints()
    # The structural "Iteration" segment is stripped: this is what WIQL wants.
    assert sprint["path"] == "Surveyor\\Release 1\\Sprint 3"
    assert sprint["name"] == "Sprint 3"


def test_azure_devops_lists_repos():
    mock = transport(
        {
            ("GET", "/Surveyor/_apis/git/repositories"): {
                "value": [
                    {
                        "name": "surveyor-web",
                        "remoteUrl": "https://dev.azure.com/emesoft/Surveyor/_git/surveyor-web",
                        "webUrl": "https://dev.azure.com/emesoft/Surveyor/_git/surveyor-web",
                        "defaultBranch": "refs/heads/main",
                    }
                ]
            }
        }
    )
    [repo] = ado_adapter(mock).list_repos()
    assert repo["name"] == "surveyor-web"
    assert repo["default_branch"] == "main"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("https://dev.azure.com/emesoft/Surveyor", ("https://dev.azure.com/emesoft", "Surveyor")),
        ("https://dev.azure.com/emesoft", ("https://dev.azure.com/emesoft", "")),
        ("dev.azure.com/emesoft/Surveyor", ("https://dev.azure.com/emesoft", "Surveyor")),
        (
            "https://dev.azure.com/emesoft/Application%20Support",
            ("https://dev.azure.com/emesoft", "Application Support"),
        ),
        (
            "https://emesoft.visualstudio.com/Surveyor",
            ("https://emesoft.visualstudio.com", "Surveyor"),
        ),
        ("", ("", "")),
        (None, ("", "")),
    ],
)
def test_parse_org_url_accepts_what_people_actually_paste(raw, expected):
    assert parse_org_url(raw) == expected


def test_azure_devops_takes_the_project_from_a_pasted_project_url():
    adapter = AzureDevOpsAdapter(
        {"baseUrl": "https://dev.azure.com/emesoft/Surveyor"}, {"pat": PAT}
    )
    assert adapter.org_url == "https://dev.azure.com/emesoft"
    assert adapter.project == "Surveyor"


ADO_PROFILE = {"id": "1a2b3c4d-0000-4444-8888-abcdefabcdef", "displayName": "Duna Nguyen"}

ADO_ACCOUNTS = {
    "count": 3,
    "value": [
        # The ordinary case.
        {"accountId": "a1", "accountName": "emesoft", "accountUri": "https://dev.azure.com/emesoft"},
        # Some tenants answer with the profile service's own address for the
        # account, which is not an API root any other call can use.
        {"accountId": "a2", "accountName": "surency", "accountUri": "https://vssps.dev.azure.com/surency"},
        # The legacy host is still live and parse_org_url reads it, so it is kept.
        {"accountId": "a3", "accountName": "contoso", "accountUri": "https://contoso.visualstudio.com"},
    ],
}


def test_azure_devops_lists_the_organizations_a_pat_can_see():
    """Two calls: the profile identifies the member, accounts answers for them."""
    mock = transport(
        {
            ("GET", "/_apis/profile/profiles/me"): ADO_PROFILE,
            ("GET", "/_apis/accounts"): ADO_ACCOUNTS,
        }
    )
    orgs = ado_adapter(mock).list_organizations()

    assert [o["name"] for o in orgs] == ["contoso", "emesoft", "surency"], "sorted by name"
    by_name = {o["name"]: o["url"] for o in orgs}
    assert by_name["emesoft"] == "https://dev.azure.com/emesoft"
    # The identity URI is replaced; the legacy host is not.
    assert by_name["surency"] == "https://dev.azure.com/surency"
    assert by_name["contoso"] == "https://contoso.visualstudio.com"

    # The member id from the profile is what accounts is asked about — asking for
    # the wrong member returns somebody else's organisations, or none.
    accounts_call = [r for r in mock.seen if r.url.path.endswith("/_apis/accounts")][0]
    assert accounts_call.url.params["memberId"] == ADO_PROFILE["id"]


def test_azure_devops_discovery_runs_against_the_profile_service_not_the_org():
    """The org URL is not merely unnecessary here — it must not be the base URL.

    Accounts live on a different host from everything else the adapter calls, and
    a request for /_apis/accounts under dev.azure.com/{org} answers 404.
    """
    mock = transport(
        {
            ("GET", "/_apis/profile/profiles/me"): ADO_PROFILE,
            ("GET", "/_apis/accounts"): ADO_ACCOUNTS,
        }
    )
    AzureDevOpsAdapter({}, {"pat": PAT}, transport=mock).list_organizations()

    assert all(r.url.host == "app.vssps.visualstudio.com" for r in mock.seen), [
        str(r.url) for r in mock.seen
    ]


def test_a_token_without_the_profile_scope_says_so_instead_of_answering_empty():
    """A work-item-only PAT gets 401 from the profile service and keeps working
    everywhere else. Reporting that as "no organisations" would read as a broken
    credential; the UI has to be able to offer manual entry instead."""
    mock = transport(
        {("GET", "/_apis/profile/profiles/me"): httpx.Response(401, json={"message": "denied"})}
    )
    with pytest.raises(ProviderError, match="vso.profile"):
        ado_adapter(mock).list_organizations()


def test_organization_discovery_never_leaks_the_pat_in_its_error():
    mock = transport({}, default_status=500)
    with pytest.raises(ProviderError) as exc:
        ado_adapter(mock).list_organizations()
    assert PAT not in str(exc.value)
    assert PAT[:12] not in str(exc.value)


def test_organization_discovery_needs_a_pat_and_nothing_else():
    with pytest.raises(ProviderError, match="PAT"):
        AzureDevOpsAdapter({}, {}).list_organizations()


def test_the_registry_still_loads_every_adapter_after_one_was_imported_directly():
    """Regression: the loader used to run only `if not _REGISTRY`.

    Importing a single adapter module — which this very test file does, and which
    any code holding a concrete adapter reference does — registers that one kind
    and makes the registry non-empty, so the emptiness check concluded the work
    was done and the other providers were never imported. It surfaced much later
    and somewhere else, as `No adapter registered for provider 'github'` on a
    connection that was configured perfectly well.

    Runs in a **subprocess** because the bug only exists on the way *into* a
    process: `register()` is an import side effect, so it fires once and cannot be
    replayed by clearing the registry — a test that cleared it in-process would
    prove nothing and would strand every later test with an empty registry.
    """
    import subprocess
    import sys

    # The trigger is the first line: one adapter module imported directly, before
    # anything asks the registry for another kind.
    script = """
from app.services.adapters.azure_devops import AzureDevOpsAdapter
from app.services.adapters import get_adapter, registered_kinds

kinds = set(registered_kinds())
assert kinds == {"azure_devops", "github", "jira"}, kinds
assert get_adapter("github", {}, {"pat": "x"}) is not None
print("ok")
"""
    result = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        cwd=str(Path(__file__).resolve().parents[1]),
    )
    assert result.returncode == 0, result.stderr
    assert "ok" in result.stdout


def test_only_azure_devops_advertises_organization_discovery():
    """The flag is what a connection form reads to choose between a picker and a
    text field, so a provider that has not implemented discovery must not claim
    it by inheriting a default."""
    assert AzureDevOpsAdapter({}, {}).supports_organizations is True
    assert GitHubAdapter({}, {}).supports_organizations is False
    assert JiraAdapter({}, {}).supports_organizations is False
    # And the fallback returns nothing rather than pretending.
    assert GitHubAdapter({}, {}).list_organizations() == []


def test_azure_devops_refuses_to_call_without_configuration():
    with pytest.raises(ProviderError, match="organisation URL"):
        AzureDevOpsAdapter({}, {"pat": PAT}).list_projects()
    with pytest.raises(ProviderError, match="PAT"):
        AzureDevOpsAdapter({"orgUrl": "https://dev.azure.com/x"}, {}).list_projects()


# ================================================================== GitHub
GITHUB_ISSUES = [
    {
        "number": 117,
        "title": "Rate limiting drops the last page",
        "state": "open",
        "html_url": "https://github.com/emesoft/hub/issues/117",
        "body": (
            "Pagination stops early.\n\n"
            "- [ ] Retry on 403 with a backoff\n"
            "- [x] Log the rate-limit headers\n"
        ),
        "labels": [{"name": "bug"}, {"name": "priority: high"}, {"name": "status: in review"}],
        "assignee": {"login": "duna"},
        "comments": 0,
    },
    # The issues endpoint also returns pull requests; they are not tickets.
    {"number": 118, "title": "A PR", "pull_request": {"url": "…"}, "labels": []},
]


def github_adapter(mock, **config):
    return GitHubAdapter({"org": "emesoft", "repo": "hub", **config}, {"pat": PAT}, transport=mock)


def test_github_normalizes_a_recorded_issue():
    mock = transport({("GET", "/repos/emesoft/hub/issues"): GITHUB_ISSUES})
    tickets = github_adapter(mock).fetch_tickets()

    assert len(tickets) == 1  # the pull request was filtered out
    ticket = tickets[0]
    assert ticket["external_id"] == "117"
    assert ticket["provider_kind"] == "github"
    assert ticket["work_item_type"] == "Bug"  # from the labels, not hardcoded
    assert ticket["status"] == "In Review"  # the `status:` label convention
    assert ticket["priority"] == "High"
    assert ticket["assignee"] == "duna"
    assert ticket["url"] == "https://github.com/emesoft/hub/issues/117"
    assert ticket["area_path"] == "emesoft/hub"
    assert ticket["acceptance_criteria"] == [
        "Retry on 403 with a backoff",
        "Log the rate-limit headers",
    ]
    assert ticket["labels"] == ["bug", "priority: high", "status: in review"]


def test_github_falls_back_to_open_closed_without_a_status_label():
    issues = [{"number": 9, "title": "Closed thing", "state": "closed", "labels": [], "body": ""}]
    mock = transport({("GET", "/repos/emesoft/hub/issues"): issues})
    [ticket] = github_adapter(mock).fetch_tickets()
    assert ticket["status"] == "Done"
    assert ticket["work_item_type"] == "Issue"


def test_github_discovers_personal_account_repos_when_the_org_endpoint_404s():
    """``/orgs/{owner}/repos`` 404s for a personal account — the adapter must
    fall through to the authenticated user's repos rather than report none."""
    mock = transport(
        {
            ("GET", "/orgs/duna/repos"): httpx.Response(404, json={"message": "Not Found"}),
            ("GET", "/user/repos"): [
                {
                    "name": "hub",
                    "owner": {"login": "Duna"},
                    "clone_url": "https://github.com/duna/hub.git",
                    "html_url": "https://github.com/duna/hub",
                    "default_branch": "master",
                },
                {"name": "someone-elses", "owner": {"login": "other"}},
            ],
        }
    )
    repos = GitHubAdapter({"org": "duna"}, {"pat": PAT}, transport=mock).list_repos()
    assert [r["name"] for r in repos] == ["hub"]
    assert repos[0]["default_branch"] == "master"


def test_github_test_connection_reports_the_login():
    mock = transport({("GET", "/user"): {"login": "duna"}})
    result = github_adapter(mock).test_connection()
    assert result == {"ok": True, "message": "Connected to GitHub as duna", "detail": {"login": "duna"}}


def test_github_enterprise_base_url_is_respected():
    assert GitHubAdapter({}, {}).api_base == "https://api.github.com"
    assert GitHubAdapter({"baseUrl": "https://github.com"}, {}).api_base == "https://api.github.com"
    assert GitHubAdapter({"baseUrl": "https://git.emesoft.net"}, {}).api_base == (
        "https://git.emesoft.net/api/v3"
    )
    assert GitHubAdapter({"baseUrl": "https://git.emesoft.net/api/v3"}, {}).api_base == (
        "https://git.emesoft.net/api/v3"
    )


# ==================================================================== Jira
JIRA_SEARCH = {
    "issues": [
        {
            "key": "SUR-412",
            "fields": {
                "summary": "Session survives a password change",
                "issuetype": {"name": "Bug"},
                "status": {"name": "In Progress"},
                "priority": {"name": "Highest"},
                "assignee": {"displayName": "Duna Nguyen"},
                "labels": ["security"],
                "description": {
                    "type": "doc",
                    "version": 1,
                    "content": [
                        {
                            "type": "paragraph",
                            "content": [{"type": "text", "text": "Old sessions stay valid."}],
                        }
                    ],
                },
                "customfield_10020": (
                    "Every session is revoked\nThe active one is kept"
                ),
                "parent": {"fields": {"summary": "Identity hardening"}},
                "comment": {
                    "comments": [
                        {
                            "author": {"displayName": "Reviewer"},
                            "created": "2026-07-20T09:00:00.000+0000",
                            "body": {
                                "type": "doc",
                                "content": [
                                    {
                                        "type": "paragraph",
                                        "content": [{"type": "text", "text": "Reproduced."}],
                                    }
                                ],
                            },
                        }
                    ]
                },
                "attachment": [{"filename": "har.json", "size": 8241}],
                "sprint": [{"name": "Sprint 3"}],
            },
        }
    ]
}


def jira_adapter(mock, **config):
    return JiraAdapter(
        {
            "baseUrl": "https://emesoft.atlassian.net",
            "project": "SUR",
            "email": "duna.nguyen@emesoft.net",
            **config,
        },
        {"pat": PAT},
        transport=mock,
    )


def test_jira_normalizes_a_recorded_issue():
    mock = transport({("POST", "/rest/api/3/search/jql"): JIRA_SEARCH})
    [ticket] = jira_adapter(mock).fetch_tickets(
        spec=TicketQuery(
            clauses=(
                QueryClause(field="iterationPath", operator="is", values=("Sprint 3",)),
            )
        )
    )

    assert ticket["external_id"] == "SUR-412"
    assert ticket["provider_kind"] == "jira"
    assert ticket["title"] == "Session survives a password change"
    assert ticket["work_item_type"] == "Bug"
    assert ticket["status"] == "In Progress"
    assert ticket["priority"] == "High"  # "Highest" collapses to High
    assert ticket["assignee"] == "Duna Nguyen"
    assert ticket["sprint"] == "Sprint 3"
    assert ticket["epic"] == "Identity hardening"
    assert ticket["description"] == "Old sessions stay valid."  # ADF flattened
    assert ticket["acceptance_criteria"] == [
        "Every session is revoked",
        "The active one is kept",
    ]
    assert ticket["comments"] == [
        {"who": "Reviewer", "when": "2026-07-20T09:00:00.000+0000", "text": "Reproduced."}
    ]
    assert ticket["attachments"] == [{"name": "har.json", "size": "8241"}]
    assert ticket["url"] == "https://emesoft.atlassian.net/browse/SUR-412"
    assert ticket["labels"] == ["security"]


def test_jira_compiles_the_selection_it_is_given():
    """The legacy `_build_jql` is gone with the `mode`/`sprint`/`states` fields it
    served (#130). Its replacement is `services.jql`, which is tested there — what is
    worth asserting here is that the adapter reaches for it.
    """
    adapter = jira_adapter(transport({}))
    assert adapter._compile(ticket_ids=["SUR-1", "SUR-2"]) == (
        'key in ("SUR-1", "SUR-2") ORDER BY updated DESC'
    )
    assert adapter._compile(
        spec=TicketQuery(
            clauses=(QueryClause(field="state", operator="is", values=("Done",)),)
        )
    ) == 'project = "SUR" AND status = "Done" ORDER BY updated DESC'


def test_jira_reads_the_email_from_config_not_from_the_secret_store():
    """One secret per connection is what lets the hub say ``hasPat`` and mean it."""
    adapter = JiraAdapter(
        {"baseUrl": "https://x.atlassian.net", "email": "duna@emesoft.net"}, {"pat": PAT}
    )
    assert adapter.email == "duna@emesoft.net"
    assert adapter.api_token == PAT
    # QAgent's key for the same value still works, for a migrated row.
    assert JiraAdapter({}, {"apiToken": "legacy"}).api_token == "legacy"


def test_jira_refuses_to_call_without_an_email_or_token():
    with pytest.raises(ProviderError, match="email"):
        JiraAdapter({"baseUrl": "https://x.atlassian.net"}, {"pat": PAT}).list_projects()
    with pytest.raises(ProviderError, match="API token"):
        JiraAdapter(
            {"baseUrl": "https://x.atlassian.net", "email": "a@b.c"}, {}
        ).list_projects()


# ============================================ never echo the PAT back out
def test_scrub_removes_a_secret_from_any_message():
    assert scrub(f"401 for token {PAT}", PAT) == f"401 for token {REDACTED}"
    # Absent or trivially short secrets leave the text alone.
    assert scrub("plain message", None) == "plain message"
    assert scrub("a-b-c", "-") == "a-b-c"


@pytest.mark.parametrize(
    ("adapter_factory", "call"),
    [
        (
            lambda mock: github_adapter(mock),
            lambda a: a.create_test_case("1", title="Reflected"),
        ),
        (
            lambda mock: jira_adapter(mock),
            lambda a: a.create_test_case("SUR-1", title="Reflected"),
        ),
        (
            lambda mock: ado_adapter(mock),
            lambda a: a.create_test_case("1", title="Reflected"),
        ),
    ],
)
def test_an_error_that_reflects_the_pat_is_scrubbed(adapter_factory, call):
    """Providers do echo credentials back in error bodies. An adapter cannot
    know when, so the removal is unconditional on every message it builds."""
    reflecting = httpx.MockTransport(
        lambda request: httpx.Response(
            401, json={"message": f"Bad credentials: {PAT} is not authorized"}
        )
    )
    with pytest.raises(ProviderError) as exc:
        call(adapter_factory(reflecting))
    assert PAT not in str(exc.value)
    assert REDACTED in str(exc.value)


def test_a_connection_failure_message_never_carries_the_pat():
    """``test_connection`` returns rather than raises, and its message is built
    from an httpx exception — the other place a credential could ride out."""

    def boom(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError(f"failed connecting with token {PAT}", request=request)

    for adapter in (
        ado_adapter(httpx.MockTransport(boom)),
        github_adapter(httpx.MockTransport(boom)),
        jira_adapter(httpx.MockTransport(boom)),
    ):
        result = adapter.test_connection()
        assert result["ok"] is False
        assert PAT not in json.dumps(result)


def test_the_registry_resolves_every_kind_and_refuses_the_rest():
    for kind in ("azure_devops", "github", "jira"):
        assert get_adapter(kind, {}, {}).kind == kind
    with pytest.raises(ProviderError, match="No adapter registered"):
        get_adapter("gitlab", {}, {})
