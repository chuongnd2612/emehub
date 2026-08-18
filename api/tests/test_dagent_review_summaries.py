"""The batch review-summary read DAgent's notification bell polls.

Driven at the HTTP seam (``_client`` / ``_get`` are replaced), because what is
worth protecting here is the *call shape* and the *failure mapping*, neither of
which a live provider is needed to observe:

* a recorded PR URL must cost two calls, not four — this endpoint replaced a
  per-ticket read precisely because the bell pays that cost on every poll;
* a URL that no longer resolves must fall back to the thorough resolution
  instead of quietly reporting "no PR", which would be an optimisation that
  empties the bell;
* one unreadable item is ``None`` in place, a whole unreadable batch raises —
  a list of nulls would render as "nothing to review" during an outage.
"""

from __future__ import annotations

import pytest

from app.services import dagent_provider
from app.services.adapters.base import ProviderError

ORG = "https://dev.azure.com/contoso"
PROJECT = "Contoso"
PR_URL = "https://dev.azure.com/contoso/Contoso/_git/web/pullrequest/42"


class FakeClient:
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _pr(pr_id: int = 42) -> dict:
    return {
        "pullRequestId": pr_id,
        "title": "Add the thing",
        "status": "active",
        "sourceRefName": "refs/heads/feature/42",
        "targetRefName": "refs/heads/main",
        "createdBy": {"displayName": "Agent"},
        "reviewers": [{"displayName": "Reviewer One"}],
        "creationDate": "2026-08-01T00:00:00Z",
        "repository": {"webUrl": f"{ORG}/{PROJECT}/_git/web", "name": "web"},
    }


def _thread(comment_id: int, text: str, status: str = "active", date: str = "2026-08-02T00:00:00Z") -> dict:
    return {
        "id": comment_id,
        "status": status,
        "threadContext": {"filePath": "/src/app.ts", "rightFileStart": {"line": 12}},
        "comments": [
            {
                "id": comment_id,
                "author": {"displayName": "Reviewer One"},
                "content": text,
                "publishedDate": date,
                "commentType": "text",
            }
        ],
    }


@pytest.fixture
def provider(monkeypatch):
    """``review_summaries`` with the provider replaced by a scripted responder.

    Returns the list of requested paths, so a test can assert how many calls a
    given input cost as well as what came back.
    """
    calls: list[str] = []

    def install(responder):
        def fake_get(client, path, pat, **params):
            calls.append(path)
            return responder(path)

        monkeypatch.setattr(dagent_provider, "_ado_context", lambda conn: (ORG, PROJECT, "pat"))
        monkeypatch.setattr(dagent_provider, "_client", lambda org, pat: FakeClient())
        monkeypatch.setattr(dagent_provider, "_get", fake_get)
        return calls

    return install


def test_a_recorded_pr_url_costs_two_calls(provider):
    """The fast path: the PR read is its own verification, so neither the work
    item nor the repository is fetched."""

    def responder(path: str):
        if path.endswith("/threads"):
            return {"value": [_thread(1, "please rename this")]}
        return _pr()

    calls = provider(responder)
    out = dagent_provider.review_summaries(object(), [{"ticketId": "77", "prUrl": PR_URL}])

    assert len(calls) == 2
    assert not any("/wit/workitems" in c for c in calls)
    assert out[0] is not None
    assert out[0]["ticketId"] == "77"
    assert out[0]["prId"] == "42"
    assert out[0]["unresolvedCount"] == 1
    assert out[0]["latestText"] == "please rename this"
    assert out[0]["prUrl"] == f"{ORG}/{PROJECT}/_git/web/pullrequest/42"


def test_only_open_threads_count_and_the_newest_one_is_carried(provider):
    def responder(path: str):
        if path.endswith("/threads"):
            return {
                "value": [
                    _thread(1, "resolved already", status="fixed", date="2026-08-02T00:00:00Z"),
                    _thread(2, "older open one", date="2026-08-03T00:00:00Z"),
                    _thread(3, "newest open one", date="2026-08-04T00:00:00Z"),
                    # A vote thread — no threadContext, so not a review comment.
                    {"id": 4, "status": "active", "comments": [{"id": 4, "content": "voted"}]},
                ]
            }
        return _pr()

    provider(responder)
    out = dagent_provider.review_summaries(object(), [{"ticketId": "77", "prUrl": PR_URL}])

    assert out[0]["unresolvedCount"] == 2
    assert out[0]["latestText"] == "newest open one"


def test_a_pr_with_nothing_open_still_reports_which_pr_it_is(provider):
    """Not a notification, but not ``None`` either: the caller needs the URL to
    stop re-resolving this ticket from its work item on every poll."""

    def responder(path: str):
        if path.endswith("/threads"):
            return {"value": [_thread(1, "done", status="closed")]}
        return _pr()

    provider(responder)
    out = dagent_provider.review_summaries(object(), [{"ticketId": "77", "prUrl": PR_URL}])

    assert out[0] is not None
    assert out[0]["unresolvedCount"] == 0
    assert out[0]["prUrl"] == f"{ORG}/{PROJECT}/_git/web/pullrequest/42"
    assert out[0]["latestText"] == ""


def test_nothing_linked_is_null(provider):
    """A work item with no PR at all — distinct from a PR with nothing open."""

    def responder(path: str):
        if "/wit/workitems/" in path:
            return {"relations": []}
        raise AssertionError(f"unexpected call: {path}")

    provider(responder)
    assert dagent_provider.review_summaries(object(), [{"ticketId": "77", "prUrl": ""}]) == [None]


def test_a_stale_pr_url_falls_back_to_the_thorough_resolution(provider):
    """A renamed repository 404s the recorded URL. The artifact link is the
    reason the slow path exists, and skipping it would empty the bell."""
    seen: dict[str, int] = {}

    def responder(path: str):
        seen[path] = seen.get(path, 0) + 1
        if "/repositories/web/" in path or path.endswith("/repositories/web"):
            raise ProviderError("404 repository not found")
        if "/wit/workitems/" in path:
            return {
                "relations": [
                    {
                        "rel": "ArtifactLink",
                        "url": "vstfs:///Git/PullRequestId/proj%2Fabc-guid%2F42",
                    }
                ]
            }
        if path.endswith("/threads"):
            return {"value": [_thread(1, "still open")]}
        if path.endswith("/repositories/abc-guid"):
            return {"project": {"name": PROJECT}}
        return _pr()

    provider(responder)
    out = dagent_provider.review_summaries(object(), [{"ticketId": "77", "prUrl": PR_URL}])

    assert out[0] is not None
    assert out[0]["unresolvedCount"] == 1
    assert any("/wit/workitems/" in p for p in seen)


def test_one_unreadable_item_is_null_in_place(provider):
    def responder(path: str):
        if "pullrequest/9" in path or "/pullrequests/9" in path:
            raise ProviderError("boom")
        if path.endswith("/threads"):
            return {"value": [_thread(1, "open")]}
        return _pr()

    provider(responder)
    out = dagent_provider.review_summaries(
        object(),
        [
            {"ticketId": "77", "prUrl": PR_URL},
            {"ticketId": "88", "prUrl": f"{ORG}/{PROJECT}/_git/web/pullrequest/9"},
        ],
    )

    assert out[0] is not None
    assert out[1] is None


def test_a_whole_unreadable_batch_raises_rather_than_answering_nulls(provider):
    """A revoked PAT fails every item. Answering ``[None, None]`` would render
    as "you have no reviews" — the ambiguity INTEGRATION.md §5 forbids."""

    def responder(path: str):
        raise ProviderError("TF400813: the user is not authorized")

    provider(responder)
    with pytest.raises(ProviderError, match="not authorized"):
        dagent_provider.review_summaries(
            object(),
            [{"ticketId": "77", "prUrl": PR_URL}, {"ticketId": "88", "prUrl": PR_URL}],
        )


def test_an_empty_request_makes_no_provider_call(provider):
    calls = provider(lambda path: {})
    assert dagent_provider.review_summaries(object(), []) == []
    assert calls == []
