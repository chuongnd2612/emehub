"""The JQL compiler, and the escaping that is its security boundary.

JQL has no parameter binding. A query is a string, so these tests are the spec for
the one thing standing between a filter value and an injected clause: **a value must
never be able to close its own literal.**

The companion of ``test_wiql.py``, deliberately mirroring its shape — the two
dialects differ but the obligations are identical.
"""

from __future__ import annotations

import pytest

from app.services import jql
from app.services.ticket_query import QueryClause, QuerySort, TicketQuery


def q(*clauses: QueryClause, match: str = "all", sort: QuerySort | None = None) -> TicketQuery:
    return TicketQuery(clauses=clauses, match=match, sort=sort or QuerySort())


def clause(field: str, operator: str, *values: str) -> QueryClause:
    return QueryClause(field=field, operator=operator, values=values)


# ─────────────────────────────────────────────────────── the escaping
def test_a_quote_cannot_close_its_own_literal():
    assert jql.quote('a" OR project = "OTHER') == '"a\\" OR project = \\"OTHER"'


def test_a_backslash_is_escaped_before_the_quote():
    """Order matters, and this is the test that pins it.

    Escaping the quote first would leave the backslash it introduced to be escaped
    by the next pass — producing a literal backslash followed by an *unescaped*
    quote, which closes the string early. That is the whole injection.
    """
    assert jql.quote('a\\"b') == '"a\\\\\\"b"'
    # The output, read as JQL, is: a \\ \" b — a backslash and a quoted quote.
    assert jql.quote("C:\\path") == '"C:\\\\path"'


def test_an_ordinary_name_with_an_apostrophe_survives():
    """Jira quotes with `"`, so an apostrophe is not special and must not be mangled."""
    assert jql.quote("O'Brien") == '"O\'Brien"'


def test_the_injection_attempt_lands_inside_the_literal():
    """The whole point, spelled out as one exact string.

    The injected text is still *present* — it is a search term now, which is what a
    filter value is — but every character it needed in order to mean anything is
    gone, and the only `ORDER BY` the parser sees is the compiler's own.
    """
    built = jql.build_jql(q(clause("title", "contains", 'a" ORDER BY key DESC -- ')), "PROJ")
    assert built == (
        'project = "PROJ" AND summary ~ "a  ORDER BY key DESC" ORDER BY updated DESC'
    )


# ───────────────────────────────────────────────────── the function allow-list
def test_the_neutral_macros_become_jira_functions():
    assert jql.function_for("@Me") == "currentUser()"
    assert jql.function_for("@me") == "currentUser()"
    assert jql.function_for("@CurrentIteration") == "openSprints()"


@pytest.mark.parametrize(
    "value",
    ["@Me OR 1=1 --", "@Nope", "currentUser()", "@ Me", "@Me()", "@"],
)
def test_a_value_that_only_looks_like_a_function_is_quoted(value):
    """The allow-list is why a `startswith("@")` test appears nowhere in the module.

    `currentUser()` typed by hand is included on purpose: a caller's bytes never
    reach the output unquoted, even when they happen to spell a real function.
    """
    assert jql.function_for(value) is None
    assert jql.operand("assignee", value) == jql.quote(value)


def test_an_allowed_function_is_re_emitted_from_the_table():
    """Not echoed. `@ME` in, the table's spelling out."""
    assert jql.operand("assignee", "@ME") == "currentUser()"


def test_current_sprint_uses_a_set_operator():
    """`sprint = openSprints()` is not valid JQL — a function returning a set needs
    `in`. Rewriting it is the difference between the preset working and a 400."""
    assert jql.clause_to_jql("iterationPath", "is", ("@CurrentIteration",)) == (
        "sprint in openSprints()"
    )
    assert jql.clause_to_jql("iterationPath", "isNot", ("@CurrentIteration",)) == (
        "sprint not in openSprints()"
    )


def test_a_named_sprint_still_uses_equality():
    assert jql.clause_to_jql("iterationPath", "is", ("Sprint 7",)) == 'sprint = "Sprint 7"'


# ────────────────────────────────────────────────────────────── dates
def test_the_date_macros_become_jira_relative_dates():
    assert jql.relative_date("@Today") == "startOfDay()"
    assert jql.relative_date("@Today - 7") == "-7d"
    assert jql.relative_date("@today-1") == "-1d"


def test_a_date_macro_offset_is_re_formatted_not_echoed():
    assert jql.relative_date("@Today -   0007") == "-7d"


def test_a_non_macro_date_is_quoted():
    assert jql.operand("changedSince", "2026-08-01") == '"2026-08-01"'


def test_a_hostile_date_is_quoted_not_passed_through():
    assert jql.operand("changedSince", '2026-01-01" OR key = "X') == jql.quote(
        '2026-01-01" OR key = "X'
    )


# ─────────────────────────────────────────────────────────── the operators
@pytest.mark.parametrize(
    "operator,expected",
    [
        ("is", 'status = "Done"'),
        ("isNot", 'status != "Done"'),
        ("in", 'status in ("Done")'),
        ("notIn", 'status not in ("Done")'),
    ],
)
def test_each_operator_compiles(operator, expected):
    assert jql.clause_to_jql("state", operator, ("Done",)) == expected


def test_a_list_operator_lists_every_value():
    assert jql.clause_to_jql("state", "in", ("A", "B", "C")) == 'status in ("A", "B", "C")'


def test_text_operators_use_the_lucene_operator():
    assert jql.clause_to_jql("title", "contains", ("login",)) == 'summary ~ "login"'
    assert jql.clause_to_jql("title", "notContains", ("login",)) == 'summary !~ "login"'


def test_lucene_syntax_in_a_text_value_becomes_spaces():
    """Replaced rather than escaped: escaping would have to survive two layers, and
    getting that wrong is exactly the bug this module exists to prevent. A space
    keeps the term matching — `sign-in` still finds the issue."""
    assert jql.quote_text("sign-in") == '"sign in"'
    assert jql.quote_text("a AND b~*") == '"a AND b"'


def test_under_is_not_compiled_for_jira():
    """Jira matches a sprint by name or id, never by a path prefix — the capability
    matrix does not offer `under`, and the compiler agrees rather than guessing."""
    assert jql.clause_to_jql("iterationPath", "under", ("Proj\\Sprint 1",)) is None


def test_a_field_jira_does_not_have_compiles_to_nothing():
    assert jql.clause_to_jql("areaPath", "under", ("Proj\\Area",)) is None


def test_an_empty_clause_says_nothing():
    assert jql.clause_to_jql("state", "is", ()) is None
    assert jql.clause_to_jql("state", "is", ("", "   ")) is None


# ───────────────────────────────────────────────────────── the project scope
def test_the_project_scope_leads_and_is_quoted():
    built = jql.build_jql(q(clause("state", "is", "Done")), "MY PROJ")
    assert built.startswith('project = "MY PROJ" AND ')


def test_an_any_query_is_parenthesised_inside_the_project_scope():
    """Without the brackets `A AND B OR C` reads as `(A AND B) OR C` and C escapes
    the project scope entirely — a filter reading another project's issues."""
    built = jql.build_jql(
        q(clause("state", "is", "Done"), clause("priority", "is", "High"), match="any"),
        "PROJ",
    )
    assert built.startswith('project = "PROJ" AND (status = "Done" OR priority = "High")')


def test_a_single_clause_needs_no_brackets():
    built = jql.build_jql(q(clause("state", "is", "Done")), "PROJ")
    assert built == 'project = "PROJ" AND status = "Done" ORDER BY updated DESC'


def test_a_query_with_no_clauses_is_just_the_project():
    assert jql.build_jql(q(), "PROJ") == 'project = "PROJ" ORDER BY updated DESC'


def test_a_hostile_project_name_cannot_break_out():
    built = jql.build_jql(q(clause("state", "is", "Done")), 'P" OR project = "OTHER')
    assert built.startswith('project = "P\\" OR project = \\"OTHER" AND ')


# ─────────────────────────────────────────────────────────────── sorting
@pytest.mark.parametrize(
    "field,expected",
    [
        ("changedDate", "updated"),
        ("createdDate", "created"),
        ("id", "key"),
        ("state", "status"),
        ("nonsense", "updated"),
    ],
)
def test_sort_fields_map(field, expected):
    built = jql.build_jql(q(sort=QuerySort(field=field, direction="asc")), "PROJ")
    assert built.endswith(f"ORDER BY {expected} ASC")


# ───────────────────────────────────────────────────── explicit selection
def test_selecting_keys_quotes_each_one():
    assert jql.issue_keys_jql(["AB-1", 'X" OR key = "Y']) == (
        'key in ("AB-1", "X\\" OR key = \\"Y")'
    )


def test_selecting_nothing_says_nothing():
    assert jql.issue_keys_jql([]) == ""
    assert jql.issue_keys_jql(["  "]) == ""


# ─────────────────────────────────── the adapter actually runs the compiled query
def _jira(handler):
    import httpx

    from app.services.adapters.jira import JiraAdapter

    return JiraAdapter(
        {"baseUrl": "https://emesoft.atlassian.net", "project": "SUR", "email": "a@b.c"},
        {"pat": "token"},
        transport=httpx.MockTransport(handler),
    )


def _capture(*, count: int | None = None):
    """Record the JQL the adapter posts, and answer with one issue."""
    import json

    import httpx

    sent: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content) if request.content else {}
        if request.url.path.endswith("/search/approximate-count"):
            sent.append(body.get("jql", ""))
            if count is None:
                return httpx.Response(404, json={})
            return httpx.Response(200, json={"count": count})
        sent.append(body.get("jql", ""))
        return httpx.Response(
            200, json={"issues": [{"key": "SUR-1", "fields": {"summary": "x"}}]}
        )

    return sent, handler


def test_a_spec_reaches_jira_as_the_compiled_jql():
    sent, handler = _capture()
    tickets = _jira(handler).fetch_tickets(
        spec=q(clause("assignee", "is", "@Me"), clause("state", "in", "Done", "Closed"))
    )
    assert len(tickets) == 1
    assert sent == [
        'project = "SUR" AND (assignee = currentUser() AND status in ("Done", "Closed")) '
        "ORDER BY updated DESC"
    ]


def test_named_keys_are_quoted_and_not_scoped_to_the_project():
    """A caller naming AB-1 has already said which issue it means; ANDing a project
    onto that could only turn a valid selection into an empty result."""
    sent, handler = _capture()
    _jira(handler).fetch_tickets(ticket_ids=["SUR-1", "SUR-2"])
    assert sent == ['key in ("SUR-1", "SUR-2") ORDER BY updated DESC']


def test_a_query_wins_over_named_keys():
    sent, handler = _capture()
    _jira(handler).fetch_tickets(spec=q(clause("state", "is", "Done")), ticket_ids=["SUR-1"])
    assert "SUR-1" not in sent[0]
    assert 'status = "Done"' in sent[0]


def test_with_neither_the_query_is_just_the_project():
    sent, handler = _capture()
    _jira(handler).fetch_tickets()
    assert sent == ['project = "SUR" ORDER BY updated DESC']


def test_counting_uses_jiras_own_count_endpoint():
    """`/search/jql` pages by token and returns no total, so a capped fetch would be
    the only other answer — and a capped number reads as the truth."""
    sent, handler = _capture(count=873)
    assert _jira(handler).count_tickets(spec=q(clause("state", "is", "Done"))) == 873
    assert sent[0].startswith('project = "SUR" AND status = "Done"')


def test_an_instance_without_the_count_endpoint_falls_back():
    """404 from `approximate-count` is an older Jira, not a failure. Falling back to
    the capped fetch is worse but still an answer."""
    sent, handler = _capture(count=None)
    assert _jira(handler).count_tickets(spec=q(clause("state", "is", "Done"))) == 1
