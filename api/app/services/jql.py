"""Compile a :class:`~app.services.ticket_query.TicketQuery` into JQL.

Pure functions, no I/O — which is what lets the injection tests run without HTTP, a
connection or an API token. The sibling of :mod:`app.services.wiql`, and it makes
the same two promises for a different dialect.

## Why the escaping in here is the security boundary

**JQL has no parameter binding.** A query is a string, and the only thing standing
between a filter value and an injected clause is :func:`quote`:

* every value is wrapped in double quotes with ``\\`` and ``"`` inside it escaped,
  in that order — escaping the quote first would then have its own backslash
  escaped and the literal would close early;
* the functions Jira understands are emitted **unquoted** — that is what makes them
  functions — and they come from an explicit allow-list keyed on the *neutral* macro
  the user picked, never from a "looks like a function" test on their bytes;
* nothing a caller typed is ever emitted unquoted.

`dev-assistant` carries a ``Project.jql`` field it treats as **trusted operator
input executed verbatim**. That posture does not carry over: we are *generating* JQL
from clauses, so every value is hostile until quoted.

## One vocabulary, four dialects

The builder offers the same neutral macros everywhere — ``@Me``,
``@CurrentIteration``, ``@Today``, ``@Today - N`` — and each compiler translates
them into its own provider's spelling. That is what lets one UI serve four
destinations without lying: the user learns one vocabulary, and Jira sees
``currentUser()`` while Azure DevOps sees ``@Me``.

## Why the project scope is always first

``project`` is the first term of every query, ANDed with everything else, and a
``match: "any"`` query wraps its clauses in one paren group. Without those brackets
``A AND B OR C`` reads as ``(A AND B) OR C`` and ``C`` escapes the project scope
entirely — which would let a filter read another project's issues.

Callers run ``ticket_query.validate`` first. This module only ever *quotes* a bad
value; it does not reject one.
"""

from __future__ import annotations

import re

from app.services.ticket_query import TicketQuery

#: JQL field per clause field.
#:
#: ``areaPath`` is absent because Jira has no area tree at all — the capability
#: matrix does not offer it, and this table is the second place that has to agree.
#:
#: ``epic`` is the classic ``Epic Link`` in company-managed projects; a
#: team-managed project models the same relationship as ``parent``, which is what
#: ``parentId`` compiles to. Both are offered because which one an instance answers
#: to is a property of the instance, not of the query.
FIELD_NAMES: dict[str, str] = {
    "workItemType": "issuetype",
    "state": "status",
    "assignee": "assignee",
    "iterationPath": "sprint",
    "tags": "labels",
    "title": "summary",
    "changedSince": "updated",
    "createdSince": "created",
    "parentId": "parent",
    "priority": "priority",
    "epic": '"Epic Link"',
}

SORT_FIELDS: dict[str, str] = {
    "changedDate": "updated",
    "createdDate": "created",
    "id": "key",
    "state": "status",
}

#: Neutral macro → the JQL function it becomes. Keyed on the macro the *builder*
#: offers, and the value is emitted from this table rather than echoed, so no part
#: of a caller's string reaches the output unquoted.
#:
#: ``@CurrentIteration`` becomes ``openSprints()``, which is the closest honest
#: equivalent: Jira has no single "current" sprint — a board can have several open
#: at once — so asking for the current one has to mean "the open ones".
FUNCTIONS: dict[str, str] = {
    "@me": "currentUser()",
    "@currentiteration": "openSprints()",
}

#: ``@Today - N`` as a JQL relative date. Jira reads ``-7d`` natively, so the
#: offset is passed to the provider to resolve rather than resolved here — the same
#: division of labour as WIQL's ``@Today - N``.
_TODAY_OFFSET = re.compile(r"^@today\s*-\s*(\d{1,4})$", re.IGNORECASE)

#: Lucene's reserved characters, which is what a JQL ``~`` text search is parsed
#: as. They are replaced with a space rather than escaped: escaping would have to
#: survive two layers (Lucene's backslash inside a JQL string literal, itself
#: backslash-escaped) and getting that wrong is exactly the bug this module exists
#: to prevent. A space is safe and keeps the term matching — ``sign-in`` becomes
#: ``sign in``, which still finds the issue.
_LUCENE_RESERVED = re.compile(r"[+\-&|!(){}\[\]^~*?:\\\"]")


def quote(value: str) -> str:
    """A value as a JQL string literal: double-quoted, ``\\`` and ``"`` escaped.

    The order matters. Escaping the quote first would leave the backslash it
    introduced to be escaped by the next pass, producing ``\\\\"`` — a literal
    backslash followed by an unescaped quote, which closes the string early. That
    is the whole injection.
    """
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def quote_text(value: str) -> str:
    """A value as the right-hand side of ``~``, with Lucene's syntax neutralised."""
    return quote(_LUCENE_RESERVED.sub(" ", value).strip())


def function_for(value: str) -> str | None:
    """The JQL function ``value`` names, or ``None`` for an ordinary value.

    The allow-list. It is why a ``startswith("@")`` test appears nowhere in this
    file: ``@Me OR 1=1 --`` starts with ``@`` and is not a macro.
    """
    return FUNCTIONS.get(value.strip().lower())


def relative_date(value: str) -> str | None:
    """``@Today``/``@Today - N`` as JQL's own relative date, or ``None``.

    ``@Today`` is ``startOfDay()`` and ``@Today - 7`` is ``-7d``. The offset is
    parsed out as digits and re-formatted, so nothing around it survives.
    """
    trimmed = value.strip()
    if trimmed.lower() == "@today":
        return "startOfDay()"
    offset = _TODAY_OFFSET.match(trimmed)
    if offset is None:
        return None
    return f"-{int(offset.group(1))}d"


def operand(field: str, value: str) -> str:
    """One operand, ready to be concatenated into JQL.

    A function or relative date goes in bare, **from the tables above**. ``parent``
    takes an issue key or id, which is quoted like anything else — Jira accepts a
    quoted key, so there is no numeric-bare exception to make here as there is in
    WIQL.
    """
    if field in ("changedSince", "createdSince"):
        relative = relative_date(value)
        if relative is not None:
            return relative
        # A plain date still has to be a string literal; Jira parses `"2026-08-01"`.
        return quote(value)
    function = function_for(value)
    if function is not None:
        return function
    return quote(value)


def clause_to_jql(field: str, operator: str, values: tuple[str, ...]) -> str | None:
    """One clause as a JQL predicate, or ``None`` when it has nothing to say."""
    name = FIELD_NAMES.get(field)
    filled = tuple(v for v in values if v.strip() != "")
    if name is None or not filled:
        return None

    first = filled[0]
    listed = ", ".join(operand(field, value) for value in filled)

    # `sprint = openSprints()` is not valid JQL — a function returning a set needs a
    # set operator. Rewriting `is` to `in` here is the difference between the
    # "current sprint" preset working and Jira answering 400.
    if operator in ("is", "isNot") and function_for(first) in ("openSprints()",):
        return f"{name} {'not in' if operator == 'isNot' else 'in'} {operand(field, first)}"

    if operator == "is":
        return f"{name} = {operand(field, first)}"
    if operator == "isNot":
        return f"{name} != {operand(field, first)}"
    if operator == "in":
        return f"{name} in ({listed})"
    if operator == "notIn":
        return f"{name} not in ({listed})"
    if operator == "contains":
        return f"{name} ~ {quote_text(first)}"
    if operator == "notContains":
        return f"{name} !~ {quote_text(first)}"
    if operator == "onOrAfter":
        return f"{name} >= {operand(field, first)}"
    if operator == "onOrBefore":
        return f"{name} <= {operand(field, first)}"
    # `under` is not offered for Jira by the capability matrix: a sprint is matched
    # by name or id, never by a path prefix.
    return None


def build_jql(query: TicketQuery, project: str) -> str:
    """The JQL for ``query``, scoped to ``project``.

    ``project`` is quoted like any other value. It arrives from the connection's
    own config rather than from a request body, but quoting it costs nothing and
    means there is no unquoted interpolation anywhere in this module to audit.
    """
    predicates = [
        predicate
        for predicate in (
            clause_to_jql(clause.field, clause.operator, clause.values)
            for clause in query.effective_clauses
        )
        if predicate is not None
    ]

    joiner = " OR " if query.match == "any" else " AND "
    combined = joiner.join(predicates)

    scope = f"project = {quote(project)}" if project.strip() else ""
    if not predicates:
        body = scope
    elif not scope:
        body = combined
    elif len(predicates) == 1:
        body = f"{scope} AND {combined}"
    else:
        # Parenthesised, so an `any` query widens within the project and never past
        # it. See the module docstring.
        body = f"{scope} AND ({combined})"

    sort_field = SORT_FIELDS.get(query.sort.field, SORT_FIELDS["changedDate"])
    direction = "ASC" if query.sort.direction == "asc" else "DESC"
    order = f"ORDER BY {sort_field} {direction}"
    return f"{body} {order}".strip() if body else order


def issue_keys_jql(ticket_ids: list[str]) -> str:
    """``key in (…)`` for an explicit selection.

    Selecting known issues is not filtering, so it has no clause form — but it does
    have the same quoting obligation, and this is the one place that meets it.
    """
    keys = [quote(t.strip()) for t in ticket_ids if t.strip()]
    return f"key in ({', '.join(keys)})" if keys else ""


__all__ = [
    "FIELD_NAMES",
    "FUNCTIONS",
    "build_jql",
    "clause_to_jql",
    "function_for",
    "issue_keys_jql",
    "operand",
    "quote",
    "quote_text",
    "relative_date",
]
