"""The GitHub search compiler — and the places GitHub genuinely cannot keep up.

Different from ``test_wiql.py`` and ``test_jql.py`` in one way that matters: GitHub
search has **no escape mechanism at all**, so the boundary here is removal rather
than escaping, and these tests pin that a value can never split into two qualifiers.

The rest is about honesty. Every assertion below where GitHub does *less* than the
other destinations is deliberate: a clause quietly dropped returns **more** tickets
than were asked for, and a `match: "any"` quietly ANDed returns fewer. Both are worse
than being told.
"""

from __future__ import annotations

import pytest

from app.services import gh_search, ticket_query
from app.services.ticket_query import QueryClause, QuerySort, TicketQuery


def q(*clauses: QueryClause, match: str = "all", sort: QuerySort | None = None) -> TicketQuery:
    return TicketQuery(clauses=clauses, match=match, sort=sort or QuerySort())


def clause(field: str, operator: str, *values: str) -> QueryClause:
    return QueryClause(field=field, operator=operator, values=values)


def built(*clauses: QueryClause, **kwargs) -> str:
    return gh_search.build_search(q(*clauses, **kwargs), org="emesoft", repo="hub")


# ──────────────────────────────────────────── what cannot be represented is removed
def test_a_quote_is_removed_because_there_is_nowhere_to_escape_it():
    """GitHub's syntax has no escape character. Removal is the only choice that
    cannot change which qualifier a value lands in."""
    assert gh_search.sanitize('a" b') == "a b"
    assert gh_search.literal('needs" triage') == '"needs triage"'


def test_a_newline_cannot_smuggle_a_second_qualifier():
    assert gh_search.sanitize("bug\nlabel:secret") == "buglabel:secret"


def test_a_value_with_a_space_is_quoted_so_it_stays_one_value():
    assert gh_search.literal("needs triage") == '"needs triage"'
    assert gh_search.literal("bug") == "bug"


def test_an_injected_qualifier_stays_inside_the_value():
    search = built(clause("tags", "is", "bug repo:someone/else"))
    assert search == 'repo:emesoft/hub is:issue label:"bug repo:someone/else"'
    # Quoted, so `repo:` is part of the label name rather than a second scope. And
    # every qualifier ANDs, so even an escaped one could only narrow.


# ───────────────────────────────────────────────────── the repo scope leads
def test_the_repo_scope_and_issue_filter_lead_every_search():
    assert built().startswith("repo:emesoft/hub is:issue")


def test_pull_requests_are_excluded_by_the_query_itself():
    assert "is:issue" in built(clause("state", "is", "open"))


# ────────────────────────────────────────────────── state: there are only two
@pytest.mark.parametrize(
    "value,expected",
    [("open", "open"), ("Closed", "closed"), ("Done", "closed"), ("In Progress", "open")],
)
def test_a_mirror_flavoured_state_is_mapped_onto_one_github_has(value, expected):
    """`state:Done` matches nothing and would read as "there is no work" rather than
    as "GitHub has two states"."""
    assert gh_search.state_for(value) == expected


def test_negating_a_state_is_the_other_state():
    """`-state:open` is not something GitHub accepts, and it does not need to be."""
    assert gh_search.clause_to_qualifiers("state", "isNot", ("open",)) == ["state:closed"]
    assert gh_search.clause_to_qualifiers("state", "isNot", ("closed",)) == ["state:open"]


# ───────────────────────────────────────────────────────────── assignee
def test_the_me_macro_becomes_githubs_own():
    assert gh_search.login_for("@Me") == "@me"
    assert gh_search.clause_to_qualifiers("assignee", "is", ("@Me",)) == ["assignee:@me"]


def test_a_value_that_only_looks_like_the_macro_is_an_ordinary_login():
    assert gh_search.login_for("@Me OR 1=1") == '"@Me OR 1=1"'


def test_negation_uses_githubs_minus_prefix():
    assert gh_search.clause_to_qualifiers("assignee", "isNot", ("octocat",)) == [
        "-assignee:octocat"
    ]


# ─────────────────────────────────────────── labels: the comma form is the OR
def test_several_labels_use_the_comma_form_because_repeating_ands_them():
    """`label:a label:b` means *both* labels — the opposite of what `in` means. This
    is the assertion that keeps that bug from coming back."""
    assert gh_search.clause_to_qualifiers("tags", "in", ("bug", "ui")) == ["label:bug,ui"]


def test_the_comma_form_is_quoted_when_a_label_has_a_space():
    assert gh_search.clause_to_qualifiers("tags", "in", ("needs triage", "ui")) == [
        'label:"needs triage,ui"'
    ]


# ───────────────────────────────────────────── type comes from the labels
def test_work_item_type_uses_the_same_label_convention_the_adapter_reads_back():
    """GitHub has no type field; the adapter *derives* one from labels when it
    normalises an issue. Filtering by type has to use the same convention or the
    filter and the rows it returns would disagree about what a Bug is."""
    assert gh_search.clause_to_qualifiers("workItemType", "is", ("Bug",)) == ["label:bug"]
    assert gh_search.clause_to_qualifiers("workItemType", "is", ("Feature",)) == [
        "label:enhancement"
    ]


def test_an_unmapped_type_becomes_a_label_of_its_own_name():
    """Emitting nothing would silently widen the search."""
    assert gh_search.clause_to_qualifiers("workItemType", "is", ("Spike",)) == ["label:Spike"]


# ─────────────────────────────────────────────────────────────── title
def test_a_title_search_is_a_term_plus_a_scope():
    assert built(clause("title", "contains", "login")) == (
        "repo:emesoft/hub is:issue login in:title"
    )


def test_one_in_title_however_many_title_clauses():
    """`in:title` scopes the search terms; it is not a filter to repeat."""
    search = built(clause("title", "contains", "login"), clause("title", "contains", "sso"))
    assert search.count("in:title") == 1


# ──────────────────────────────────────────────────────────────── dates
def test_a_date_macro_is_resolved_here_because_github_will_not():
    """Azure DevOps and Jira expand `@Today - 7` themselves. GitHub does not, so a
    compiler that passed it through would compare against the literal text and match
    nothing."""
    from datetime import date

    resolved = gh_search.date_for("@Today")
    assert resolved == date.today().isoformat()
    assert gh_search.clause_to_qualifiers("changedSince", "onOrAfter", ("@Today",)) == [
        f"updated:>={date.today().isoformat()}"
    ]


def test_the_two_date_fields_and_both_comparators():
    assert gh_search.clause_to_qualifiers("createdSince", "onOrBefore", ("2026-01-01",)) == [
        "created:<=2026-01-01"
    ]
    assert gh_search.clause_to_qualifiers("changedSince", "onOrAfter", ("2026-01-01",)) == [
        "updated:>=2026-01-01"
    ]


# ─────────────────────────────────── fields GitHub does not have say nothing
@pytest.mark.parametrize("field", ["areaPath", "iterationPath", "parentId", "priority", "epic"])
def test_a_concept_github_does_not_have_compiles_to_nothing(field):
    """And the capability matrix does not offer them, which is what stops a clause
    getting this far in the first place."""
    assert gh_search.clause_to_qualifiers(field, "is", ("x",)) == []
    assert ticket_query.operators_for("github", field) == ()


def test_an_empty_clause_says_nothing():
    assert gh_search.clause_to_qualifiers("state", "is", ()) == []
    assert gh_search.clause_to_qualifiers("state", "is", ("  ",)) == []


# ─────────────────────────────────────── the one capability that is about the join
def test_an_any_query_is_refused_for_github_rather_than_silently_anded():
    """GitHub search ANDs every qualifier and has no OR and no grouping. Compiling
    `any` as AND would return *fewer* tickets than asked for, silently — the failure
    the whole capability matrix exists to prevent."""
    problems = ticket_query.validate(
        q(clause("state", "is", "open"), clause("assignee", "is", "@Me"), match="any"),
        "github",
    )
    assert any("cannot combine conditions" in p.message for p in problems)


def test_an_any_query_is_fine_everywhere_else():
    for destination in ("azure_devops", "jira", "mirror"):
        problems = ticket_query.validate(
            q(clause("state", "is", "Active"), clause("title", "contains", "x"), match="any"),
            destination,
        )
        assert problems == [], f"{destination} refused a valid `any` query"


# ─────────────────────────────────────────────────────────────── sorting
def test_sort_goes_in_its_own_parameters_not_the_query():
    assert gh_search.sort_params(q(sort=QuerySort(field="createdDate", direction="asc"))) == {
        "sort": "created",
        "order": "asc",
    }
    assert gh_search.sort_params(q())["sort"] == "updated"


def test_a_full_query_compiles_end_to_end():
    search = built(
        clause("state", "is", "open"),
        clause("assignee", "is", "@Me"),
        clause("tags", "in", "bug", "ui"),
    )
    assert search == "repo:emesoft/hub is:issue state:open assignee:@me label:bug,ui"


# ─────────────────────────────────── the adapter actually runs the compiled query
def _github(handler):
    import httpx

    from app.services.adapters.github import GitHubAdapter

    return GitHubAdapter(
        {"org": "emesoft", "repo": "hub"}, {"pat": "token"}, transport=httpx.MockTransport(handler)
    )


def _capture(*, total: int = 1, items: list | None = None):
    """Record every path and query the adapter asks for."""
    import httpx

    seen: list[tuple[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append((request.url.path, request.url.params.get("q", "")))
        if request.url.path == "/search/issues":
            return httpx.Response(
                200,
                json={
                    "total_count": total,
                    "items": items
                    if items is not None
                    else [{"number": 7, "title": "x", "state": "open", "labels": []}],
                },
            )
        return httpx.Response(200, json=[])

    return seen, handler


def test_a_spec_goes_through_the_search_api_not_the_issues_list():
    """`/repos/…/issues` has no query language at all, which is why the old adapter
    silently ignored states/types/area. The search API is the only one that can
    honour a clause."""
    seen, handler = _capture()
    tickets = _github(handler).fetch_tickets(
        spec=q(clause("state", "is", "open"), clause("tags", "in", "bug", "ui"))
    )
    assert len(tickets) == 1
    assert seen[0][0] == "/search/issues"
    assert seen[0][1] == "repo:emesoft/hub is:issue state:open label:bug,ui"


def test_the_legacy_path_still_uses_the_issues_list():
    seen, handler = _capture()
    _github(handler).fetch_tickets(mode="all")
    assert seen[0][0] == "/repos/emesoft/hub/issues"


def test_a_spec_replaces_the_legacy_selection_rather_than_blending_with_it():
    seen, handler = _capture()
    _github(handler).fetch_tickets(spec=q(clause("state", "is", "open")), mode="assigned")
    assert [path for path, _ in seen] == ["/search/issues"]
    # `mode="assigned"` would have called /user to resolve the login. It did not.


def test_pull_requests_are_dropped_even_if_the_search_returns_one():
    seen, handler = _capture(
        items=[
            {"number": 1, "title": "issue", "state": "open", "labels": []},
            {"number": 2, "title": "pr", "state": "open", "labels": [], "pull_request": {}},
        ]
    )
    tickets = _github(handler).fetch_tickets(spec=q(clause("state", "is", "open")))
    assert [t["external_id"] for t in tickets] == ["1"]


def test_counting_reads_the_search_apis_own_total():
    """A page size is the wrong answer to "how many are there"."""
    seen, handler = _capture(total=873)
    assert _github(handler).count_tickets(spec=q(clause("state", "is", "open"))) == 873


def test_a_malformed_search_surfaces_githubs_message_rather_than_no_results():
    import httpx

    from app.services.adapters.base import ProviderError

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(422, json={"message": "Validation Failed"})

    with pytest.raises(ProviderError, match="rejected the search"):
        _github(handler).fetch_tickets(spec=q(clause("state", "is", "open")))


def test_the_pat_is_never_echoed_in_a_rejection():
    import httpx

    from app.services.adapters.base import ProviderError

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(422, text="bad token token")

    with pytest.raises(ProviderError) as caught:
        _github(handler).fetch_tickets(spec=q(clause("state", "is", "open")))
    assert "token" not in str(caught.value).replace("«redacted»", "")
