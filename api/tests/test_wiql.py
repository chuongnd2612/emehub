"""The WIQL compiler, and the escaping that is its whole point.

WIQL has no parameter binding: a query is a string, so `quote` and the macro
allow-list are the only thing between a filter value and an injected clause. The
injection cases below are ported verbatim from
`dev-assistant/packages/shared/src/filter.test.ts` — they are the spec, not
decoration.
"""

from __future__ import annotations

import json

import httpx
import pytest

from app.services import wiql
from app.services.ticket_query import QueryClause, QuerySort, TicketQuery

PROJECT = "Surency"


def q(*clauses: QueryClause, match: str = "all", **sort) -> TicketQuery:
    return TicketQuery(
        clauses=tuple(clauses),
        match=match,
        sort=QuerySort(**sort) if sort else QuerySort(),
    )


def c(field: str, operator: str, *values: str) -> QueryClause:
    return QueryClause(field=field, operator=operator, values=tuple(values))


def build(*clauses: QueryClause, match: str = "all", **sort) -> str:
    return wiql.build_wiql(q(*clauses, match=match, **sort), PROJECT)


# ───────────────────────────────────────────────────── escaping and macros
def test_a_value_cannot_close_its_own_literal():
    """The whole defence: WIQL's own escape, single quotes doubled."""
    assert wiql.quote("O'Brien") == "'O''Brien'"
    assert wiql.quote("plain") == "'plain'"


def test_the_ported_injection_case():
    """Verbatim from dev-assistant's suite. The payload lands inside the literal
    with its quote doubled, so it is data rather than syntax."""
    built = build(c("title", "contains", "a' ORDER BY [System.Id] --"))
    assert "[System.Title] CONTAINS 'a'' ORDER BY [System.Id] --'" in built


def test_the_second_ported_injection_case():
    built = build(c("title", "contains", "x') OR 1=1 --"))
    assert "[System.Title] CONTAINS 'x'') OR 1=1 --'" in built


@pytest.mark.parametrize(
    ("value", "expected"),
    [("@Me", "@Me"), ("@me", "@Me"), ("  @ME  ", "@Me"), ("@CurrentIteration", "@CurrentIteration")],
)
def test_an_allowed_macro_is_recognised_and_re_emitted_from_the_list(value, expected):
    """Re-emitted from the allow-list, never echoed — so no part of the caller's
    string reaches the output unquoted."""
    assert wiql.macro_for(value) == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [("@Today - 7", "@Today - 7"), ("@today-1", "@Today - 1"), ("@Today   -   30", "@Today - 30")],
)
def test_the_one_macro_with_an_argument_is_parsed_and_reformatted(value, expected):
    """The offset is parsed out as digits and re-formatted, so nothing around it
    survives into the output."""
    assert wiql.macro_for(value) == expected


@pytest.mark.parametrize(
    "value",
    [
        "@Me OR 1=1",
        "@Me OR 1=1 --",
        "@Nope",
        "@",
        "@Today - 7; DROP",
        "@Today - abc",
        "not a macro",
    ],
)
def test_anything_that_merely_looks_like_a_macro_is_quoted(value):
    """This is why there is no `startswith('@')` test anywhere in the module."""
    assert wiql.macro_for(value) is None
    assert wiql.operand("assignee", value) == wiql.quote(value)


def test_a_macro_goes_in_bare_and_a_value_does_not():
    assert "[System.AssignedTo] = @Me" in build(c("assignee", "is", "@Me"))
    assert "[System.AssignedTo] = 'duna'" in build(c("assignee", "is", "duna"))


def test_parent_id_is_bare_for_digits_and_quoted_otherwise():
    """System.Parent is an integer field and ADO rejects a quoted number there.
    Digits cannot carry an injection; anything else is quoted so it fails as the
    type error it is."""
    assert "[System.Parent] = 1428" in build(c("parentId", "is", "1428"))
    assert "[System.Parent] = '1428 OR 1=1'" in build(c("parentId", "is", "1428 OR 1=1"))


# ─────────────────────────────────────────────────────────── query shape
def test_the_project_scope_is_always_the_first_term():
    """A query may narrow the result and must never widen past the project."""
    for built in (build(), build(c("state", "is", "Active"))):
        assert built.startswith("SELECT [System.Id] FROM WorkItems WHERE [System.TeamProject] = 'Surency'")


def test_an_empty_query_is_just_the_project():
    assert build() == (
        "SELECT [System.Id] FROM WorkItems WHERE [System.TeamProject] = 'Surency' "
        "ORDER BY [System.ChangedDate] DESC"
    )


def test_one_clause_needs_no_brackets():
    assert build(c("assignee", "is", "@Me")) == (
        "SELECT [System.Id] FROM WorkItems WHERE [System.TeamProject] = 'Surency' "
        "AND [System.AssignedTo] = @Me ORDER BY [System.ChangedDate] DESC"
    )


def test_an_any_query_is_parenthesised():
    """Without the brackets `A AND B OR C` reads as `(A AND B) OR C`, and C escapes
    the project scope entirely."""
    built = build(c("assignee", "is", "@Me"), c("state", "is", "Active"), match="any")
    assert built == (
        "SELECT [System.Id] FROM WorkItems WHERE [System.TeamProject] = 'Surency' "
        "AND ([System.AssignedTo] = @Me OR [System.State] = 'Active') "
        "ORDER BY [System.ChangedDate] DESC"
    )


def test_an_all_query_is_also_grouped():
    built = build(c("state", "is", "Active"), c("workItemType", "is", "Bug"))
    assert "AND ([System.State] = 'Active' AND [System.WorkItemType] = 'Bug')" in built


@pytest.mark.parametrize(
    ("operator", "expected"),
    [
        ("is", "[System.State] = 'Active'"),
        ("isNot", "[System.State] <> 'Active'"),
        ("contains", "[System.State] CONTAINS 'Active'"),
        ("notContains", "[System.State] NOT CONTAINS 'Active'"),
        ("under", "[System.State] UNDER 'Active'"),
        ("onOrAfter", "[System.State] >= 'Active'"),
        ("onOrBefore", "[System.State] <= 'Active'"),
    ],
)
def test_every_single_value_operator(operator, expected):
    assert expected in build(c("state", operator, "Active"))


def test_the_list_operators():
    assert "[System.State] IN ('Active', 'New')" in build(c("state", "in", "Active", "New"))
    assert "[System.State] NOT IN ('Active', 'New')" in build(c("state", "notIn", "Active", "New"))


def test_a_clause_of_only_blanks_is_dropped_rather_than_compiled_to_empty():
    """`field = ''` matches nothing and reads as "there is no work" rather than as
    the user's own unfinished input."""
    built = build(c("state", "is", "  "), c("title", "contains", "boom"))
    assert "[System.State]" not in built
    assert "[System.Title] CONTAINS 'boom'" in built


def test_blanks_inside_a_list_are_dropped():
    assert "[System.State] IN ('Active')" in build(c("state", "in", "Active", "", "  "))


def test_an_unknown_field_compiles_to_nothing():
    """Validation refuses these first; the compiler still must not emit
    `[None] = 'x'` if one slips through."""
    assert wiql.clause_to_wiql("nonsense", "is", ("x",)) is None
    assert build(c("nonsense", "is", "x")) == build()


def test_epic_is_absent_because_ado_has_no_epic_field():
    """An epic in ADO is a work item type reached through System.Parent, not a
    field. The capability matrix omits it for this destination and so does this
    table — the two have to agree."""
    assert "epic" not in wiql.FIELD_REFERENCE_NAMES


# ───────────────────────────────────────────────────────────────── sorting
@pytest.mark.parametrize(
    ("field", "column"),
    [
        ("changedDate", "System.ChangedDate"),
        ("createdDate", "System.CreatedDate"),
        ("id", "System.Id"),
        ("state", "System.State"),
    ],
)
def test_every_sort_field(field, column):
    assert build(c("state", "is", "Active"), field=field).endswith(f"ORDER BY [{column}] DESC")


def test_sort_direction():
    built = build(c("state", "is", "Active"), field="id", direction="asc")
    assert built.endswith("ORDER BY [System.Id] ASC")


def test_an_unknown_sort_field_falls_back_rather_than_emitting_it():
    built = wiql.build_wiql(
        TicketQuery(clauses=(c("state", "is", "A"),), sort=QuerySort(field="'; DROP--")),
        PROJECT,
    )
    assert built.endswith("ORDER BY [System.ChangedDate] DESC")


def test_the_project_name_is_quoted_too():
    assert "[System.TeamProject] = 'O''Brien Ltd'" in wiql.build_wiql(q(), "O'Brien Ltd")


# ───────────────────────────────────── the adapter actually runs the compiled query
def _ado(handler):
    from app.services.adapters.azure_devops import AzureDevOpsAdapter

    return AzureDevOpsAdapter(
        {"orgUrl": "https://dev.azure.com/emesoft", "project": "Surveyor"},
        {"pat": "pat"},
        transport=httpx.MockTransport(handler),
    )


def _capture(status: int = 200):
    """Record the WIQL the adapter posts, and answer with one work item."""
    sent: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/wiql"):
            sent.append(json.loads(request.content)["query"])
            if status != 200:
                return httpx.Response(status, json={"message": "TF51005: bad field"})
            return httpx.Response(200, json={"workItems": [{"id": 7}]})
        return httpx.Response(
            200,
            json={"value": [{"id": 7, "fields": {"System.Title": "x", "System.State": "Active"}}]},
        )

    return sent, handler


def test_a_spec_reaches_azure_devops_as_the_compiled_query():
    sent, handler = _capture()
    tickets = _ado(handler).fetch_tickets(
        spec=q(c("assignee", "is", "@Me"), c("state", "in", "Active", "New"))
    )
    assert len(tickets) == 1
    assert sent == [
        "SELECT [System.Id] FROM WorkItems WHERE [System.TeamProject] = 'Surveyor' "
        "AND ([System.AssignedTo] = @Me AND [System.State] IN ('Active', 'New')) "
        "ORDER BY [System.ChangedDate] DESC"
    ]


def test_named_ids_skip_the_query_entirely():
    """Selecting known work items is not filtering: no WIQL is built, and no
    round-trip is spent asking ADO which ids match a list of ids."""
    sent, handler = _capture()
    _ado(handler).fetch_tickets(ticket_ids=["7", "9"])
    assert sent == []


def test_a_non_numeric_id_is_dropped_rather_than_sent():
    """`System.Id` is an integer field, so ADO would reject the whole batch — losing
    the ids that were fine along with the one that was not."""
    sent, handler = _capture()
    tickets = _ado(handler).fetch_tickets(ticket_ids=["7", "not-an-id"])
    assert sent == []
    assert len(tickets) == 1


def test_a_query_wins_over_named_ids():
    """Both can arrive; the query is the filter and the more specific instruction."""
    sent, handler = _capture()
    _ado(handler).fetch_tickets(spec=q(c("state", "is", "Active")), ticket_ids=["7"])
    assert len(sent) == 1
    assert "[System.State] = 'Active'" in sent[0]


def test_with_neither_the_query_is_just_the_project():
    """The router refuses this case (`SyncRequest` requires one of the two), but the
    adapter still has to mean something rather than crash."""
    sent, handler = _capture()
    _ado(handler).fetch_tickets()
    assert sent == [
        "SELECT [System.Id] FROM WorkItems WHERE [System.TeamProject] = 'Surveyor' "
        "ORDER BY [System.ChangedDate] DESC"
    ]


def test_a_rejected_clause_query_is_not_silently_retried_unscoped():
    """The legacy sprint retry exists because `mode="sprint"` DERIVES an iteration
    path the caller never saw. A clause query contains only paths the user picked,
    so a 400 is a real answer — retrying without the condition would return more
    work items than were asked for."""
    from app.services.adapters.base import ProviderError

    sent, handler = _capture(status=400)
    with pytest.raises(ProviderError, match="rejected the query"):
        _ado(handler).fetch_tickets(spec=q(c("state", "is", "Active")))
    assert len(sent) == 1
