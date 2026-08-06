"""Compile a :class:`~app.services.ticket_query.TicketQuery` into WIQL.

Ported from ``dev-assistant/packages/shared/src/filter.ts``. Pure functions, no
I/O — which is what lets the injection tests run without HTTP, a connection or a
PAT.

## Why the escaping in here is the security boundary

**WIQL has no parameter binding.** A query is a string, and the only thing standing
between a filter value and an injected clause is :func:`quote`. So:

* every value is wrapped in single quotes with the single quotes inside it doubled
  (``O'Brien`` → ``'O''Brien'``). That is WIQL's own escape, and it makes it
  impossible for a value to close its own literal;
* the macros Azure DevOps understands are emitted **unquoted** — that is what makes
  them macros — and they are recognised by an explicit allow-list, never by a
  "starts with ``@``" test. A value that merely looks like a macro (``@Me OR 1=1``,
  ``@Nope``) is quoted as the literal it is;
* an allowed macro is **re-emitted from the allow-list**, never echoed from the
  input, so no part of a caller's string reaches the output unquoted.

## Why the project scope is always first

``[System.TeamProject]`` is the first term of every query, ANDed with everything
else. A ``match: "any"`` query wraps its clauses in one paren group, so an OR can
widen the result *within* the project and never past it. Getting that wrong would
let a filter read another project's work items.

Callers run ``ticket_query.validate`` first. This module only ever *quotes* a bad
value; it does not reject one.
"""

from __future__ import annotations

import re

from app.services.ticket_query import TicketQuery

#: Azure DevOps reference name per clause field.
#:
#: ``epic`` is absent: ADO has no epic field — an epic is a work item type, reached
#: through ``System.Parent``. The capability matrix already omits it for this
#: destination, and this table is the second place that has to agree.
FIELD_REFERENCE_NAMES: dict[str, str] = {
    "workItemType": "System.WorkItemType",
    "state": "System.State",
    "assignee": "System.AssignedTo",
    "areaPath": "System.AreaPath",
    "iterationPath": "System.IterationPath",
    "tags": "System.Tags",
    "title": "System.Title",
    "changedSince": "System.ChangedDate",
    "createdSince": "System.CreatedDate",
    "parentId": "System.Parent",
    "priority": "Microsoft.VSTS.Common.Priority",
}

SORT_FIELDS: dict[str, str] = {
    "changedDate": "System.ChangedDate",
    "createdDate": "System.CreatedDate",
    "id": "System.Id",
    "state": "System.State",
}

#: The macros that may be emitted unquoted, and nothing else.
#:
#: Matched exactly and case-insensitively (ADO accepts ``@me``), then re-emitted in
#: the canonical spelling **from this tuple** rather than echoed, so the caller's
#: bytes never leave the quoting path.
EXACT_MACROS: tuple[str, ...] = ("@Me", "@CurrentIteration", "@Today")

#: ``@Today - N`` — the only macro with an argument, and the argument is digits.
#: The offset is parsed out and re-formatted, so nothing around it survives.
_TODAY_OFFSET = re.compile(r"^@today\s*-\s*(\d{1,4})$", re.IGNORECASE)


def macro_for(value: str) -> str | None:
    """The macro ``value`` is, or ``None`` when it is an ordinary value.

    This is the allow-list, and it is why a ``startswith("@")`` test appears
    nowhere in this file: ``@Me OR 1=1 --`` starts with ``@`` and is not a macro.
    """
    trimmed = value.strip()
    for macro in EXACT_MACROS:
        if trimmed.lower() == macro.lower():
            return macro
    offset = _TODAY_OFFSET.match(trimmed)
    if offset is not None:
        return f"@Today - {int(offset.group(1))}"
    return None


def is_macro(value: str) -> bool:
    """True when Azure DevOps will expand ``value``."""
    return macro_for(value) is not None


def quote(value: str) -> str:
    """A value as a WIQL string literal: single-quoted, inner quotes doubled.

    WIQL's own escape, and the whole defence.
    """
    escaped = value.replace("'", "''")
    return f"'{escaped}'"


def operand(field: str, value: str) -> str:
    """One operand, ready to be concatenated into WIQL.

    A macro goes in bare, from the allow-list. ``parentId`` goes in bare when it is
    all digits, because ``System.Parent`` is an integer field and ADO rejects a
    quoted number there — and digits cannot carry an injection. Everything else is
    quoted, including a non-numeric ``parentId``, which then fails in ADO as the
    type error it is rather than as an injection.
    """
    macro = macro_for(value)
    if macro is not None:
        return macro
    if field == "parentId" and value.strip().isdigit():
        return value.strip()
    return quote(value)


def clause_to_wiql(field: str, operator: str, values: tuple[str, ...]) -> str | None:
    """One clause as a WIQL predicate, or ``None`` when it has nothing to say."""
    reference = FIELD_REFERENCE_NAMES.get(field)
    filled = tuple(v for v in values if v.strip() != "")
    if reference is None or not filled:
        return None

    column = f"[{reference}]"
    first = filled[0]
    listed = ", ".join(operand(field, value) for value in filled)

    if operator == "is":
        return f"{column} = {operand(field, first)}"
    if operator == "isNot":
        return f"{column} <> {operand(field, first)}"
    if operator == "in":
        return f"{column} IN ({listed})"
    if operator == "notIn":
        return f"{column} NOT IN ({listed})"
    if operator == "contains":
        return f"{column} CONTAINS {operand(field, first)}"
    if operator == "notContains":
        return f"{column} NOT CONTAINS {operand(field, first)}"
    if operator == "under":
        return f"{column} UNDER {operand(field, first)}"
    if operator == "onOrAfter":
        return f"{column} >= {operand(field, first)}"
    if operator == "onOrBefore":
        return f"{column} <= {operand(field, first)}"
    return None


def build_wiql(query: TicketQuery, project: str) -> str:
    """The ids-only WIQL for ``query``, scoped to ``project``.

    ``SELECT [System.Id]`` and no fields: the values come from the batched
    work-item read that follows, which is how the REST API is shaped and how the
    read stays under ADO's 200-id cap.
    """
    scope = f"[System.TeamProject] = {quote(project)}"
    predicates = [
        predicate
        for predicate in (
            clause_to_wiql(clause.field, clause.operator, clause.values)
            for clause in query.effective_clauses
        )
        if predicate is not None
    ]

    joiner = " OR " if query.match == "any" else " AND "
    combined = joiner.join(predicates)
    if not predicates:
        body = scope
    elif len(predicates) == 1:
        body = f"{scope} AND {combined}"
    else:
        # Parenthesised, so an `any` query can widen within the project and never
        # past it. Without these brackets `A AND B OR C` reads as `(A AND B) OR C`
        # and C escapes the project scope entirely.
        body = f"{scope} AND ({combined})"

    sort_field = SORT_FIELDS.get(query.sort.field, SORT_FIELDS["changedDate"])
    direction = "ASC" if query.sort.direction == "asc" else "DESC"
    return f"SELECT [System.Id] FROM WorkItems WHERE {body} ORDER BY [{sort_field}] {direction}"
