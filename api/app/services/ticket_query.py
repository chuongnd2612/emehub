"""The ticket query model: clauses, the capability matrix, validation.

Ported from ``dev-assistant/packages/shared/src/filter.ts``, which is ~490 lines of
pure functions with no I/O and no dependencies — which is why it ports almost line
for line, and why the reasoning in its comments is worth carrying over rather than
rediscovering.

## What a query is

A **flat** list of clauses plus one global ``match``. There is no nesting and no
per-clause conjunction, deliberately: mixed AND/OR trees are a large jump in both
UI and compiler complexity, and every query anyone has actually asked for is
expressible without them.

## One model, several destinations

A query is provider-agnostic. Each *destination* compiles it into its own dialect —
WIQL for Azure DevOps, JQL for Jira, search qualifiers for GitHub, SQLAlchemy for
the hub's own mirror. Since the three providers genuinely differ in what they can
express, :data:`CAPABILITIES` says per destination which fields exist and which
operators each field allows.

**That matrix is what keeps a single builder honest.** Without it, a UI offering
every field for every provider would produce clauses GitHub silently ignores — and
a silently ignored clause returns *more* tickets than were asked for, which is the
worst possible failure for a filter.

## Where the security boundary is (and is not)

It is **not** here. This module validates and describes; it never builds a query
string. WIQL and JQL have no parameter binding, so their compilers own the
escaping, and each lives beside the adapter that speaks the dialect. What this
module contributes is the guarantee that a clause reaching a compiler has a known
field and a known operator — so a compiler never has to decide what to do with
something unrecognised.
"""

from __future__ import annotations

from dataclasses import dataclass, field as dc_field
from typing import Any, Literal

# ─────────────────────────────────────────────────────────────── the vocabulary

#: Fields a clause can constrain, as the UI names them. Provider-neutral: the
#: mapping onto ``System.WorkItemType`` / ``issuetype`` / ``label:`` belongs to
#: each compiler, not here.
ClauseField = Literal[
    "workItemType",
    "state",
    "assignee",
    "areaPath",
    "iterationPath",
    "tags",
    "title",
    "changedSince",
    "createdSince",
    "parentId",
    "priority",
    "epic",
]

ClauseOperator = Literal[
    "is",
    "isNot",
    "in",
    "notIn",
    "contains",
    "notContains",
    "under",
    "onOrAfter",
    "onOrBefore",
]

SortField = Literal["changedDate", "createdDate", "id", "state"]
SortDirection = Literal["asc", "desc"]

#: Where a query is going. ``mirror`` is the hub's own ``tickets`` table.
Destination = Literal["azure_devops", "jira", "github", "mirror"]

#: The only operators that take more than one value.
LIST_OPERATORS: frozenset[str] = frozenset({"in", "notIn"})

FIELD_LABELS: dict[str, str] = {
    "workItemType": "work item type",
    "state": "state",
    "assignee": "assigned to",
    "areaPath": "area path",
    "iterationPath": "sprint",
    "tags": "tags",
    "title": "title",
    "changedSince": "changed date",
    "createdSince": "created date",
    "parentId": "parent",
    "priority": "priority",
    "epic": "epic",
}

OPERATOR_LABELS: dict[str, str] = {
    "is": "is",
    "isNot": "is not",
    "in": "is any of",
    "notIn": "is none of",
    "contains": "contains",
    "notContains": "does not contain",
    "under": "under",
    "onOrAfter": "on or after",
    "onOrBefore": "on or before",
}

SORT_FIELDS: frozenset[str] = frozenset({"changedDate", "createdDate", "id", "state"})
SORT_DIRECTIONS: frozenset[str] = frozenset({"asc", "desc"})


# ─────────────────────────────────────────────────────────── the capability matrix

#: Operator sets, named so the matrix below reads as intent rather than as lists.
#:
#: ``_EQUALITY`` is the ordinary "one of these values" set. ``_PATH`` leads with
#: ``under`` because ``=`` on an area or iteration path silently excludes every
#: child, which is almost never what the user meant. ``_TEXT`` is substring only.
#: ``_DATE`` gets the two range operators and nothing else — a work item is never
#: changed *at* exactly a date.
_EQUALITY: tuple[str, ...] = ("is", "isNot", "in", "notIn")
_PATH: tuple[str, ...] = ("under", "is", "isNot")
_TEXT: tuple[str, ...] = ("contains", "notContains")
_DATE: tuple[str, ...] = ("onOrAfter", "onOrBefore")

#: What each destination can actually run.
#:
#: A field absent from a destination is **not offered** for it, which is the
#: honest alternative to accepting a clause and dropping it. The differences are
#: real, not conservatism:
#:
#: * **Azure DevOps** — full WIQL. Every field, every operator.
#: * **Jira** — JQL has no area-path tree at all, so ``areaPath`` is absent.
#:   Sprints are matched by name or id, not by a path prefix, so ``iterationPath``
#:   loses ``under``.
#: * **GitHub** — the search API has qualifiers, not a query language. No area, no
#:   sprint, no parent, no priority, no epic; ``state``/``assignee``/``tags`` take
#:   equality and negation only, and ``title`` is the ``in:title`` qualifier.
#: * **mirror** — parameterised SQL over our own columns, so it can honour
#:   everything the columns hold. It has no ``parentId`` column, and that is the
#:   only gap.
CAPABILITIES: dict[str, dict[str, tuple[str, ...]]] = {
    "azure_devops": {
        "workItemType": _EQUALITY,
        "state": _EQUALITY,
        "assignee": _EQUALITY,
        "areaPath": _PATH,
        "iterationPath": _PATH,
        "tags": _TEXT,
        "title": _TEXT,
        "changedSince": _DATE,
        "createdSince": _DATE,
        "parentId": _EQUALITY,
        "priority": _EQUALITY,
    },
    "jira": {
        "workItemType": _EQUALITY,
        "state": _EQUALITY,
        "assignee": _EQUALITY,
        "iterationPath": ("is", "isNot", "in", "notIn"),
        "tags": _EQUALITY,
        "title": _TEXT,
        "changedSince": _DATE,
        "createdSince": _DATE,
        "parentId": ("is", "isNot"),
        "priority": _EQUALITY,
        "epic": ("is", "isNot", "in", "notIn"),
    },
    "github": {
        "state": ("is", "isNot"),
        "assignee": ("is", "isNot"),
        "tags": ("is", "isNot", "in"),
        "title": ("contains",),
        "changedSince": _DATE,
        "createdSince": _DATE,
        "workItemType": ("is",),
    },
    "mirror": {
        "workItemType": _EQUALITY,
        "state": _EQUALITY,
        "assignee": _EQUALITY,
        "areaPath": _PATH,
        "iterationPath": _PATH,
        "tags": _TEXT,
        "title": _TEXT,
        "changedSince": _DATE,
        "createdSince": _DATE,
        "priority": _EQUALITY,
        "epic": _EQUALITY,
    },
}


def fields_for(destination: str) -> tuple[str, ...]:
    """The fields ``destination`` can filter on, in the matrix's own order."""
    return tuple(CAPABILITIES.get(destination, {}))


def operators_for(destination: str, field: str) -> tuple[str, ...]:
    """The operators ``destination`` allows on ``field``; empty when unsupported."""
    return CAPABILITIES.get(destination, {}).get(field, ())


# ───────────────────────────────────────────────────────────────── the query

@dataclass(frozen=True)
class QueryClause:
    field: str
    operator: str
    values: tuple[str, ...] = ()

    @property
    def filled(self) -> tuple[str, ...]:
        """The values that are not blank. A clause of only blanks is inert."""
        return tuple(v for v in self.values if v.strip() != "")


@dataclass(frozen=True)
class QuerySort:
    field: str = "changedDate"
    direction: str = "desc"


@dataclass(frozen=True)
class TicketQuery:
    clauses: tuple[QueryClause, ...] = ()
    #: ``all`` joins with AND, ``any`` with OR. Flat — see the module docstring.
    match: str = "all"
    sort: QuerySort = dc_field(default_factory=QuerySort)

    @property
    def effective_clauses(self) -> tuple[QueryClause, ...]:
        """Clauses with at least one non-blank value — what a compiler emits.

        A half-typed clause must not become ``field = ''``, which matches nothing
        and reads to the user as "there is no work" rather than as their own
        unfinished input.
        """
        return tuple(c for c in self.clauses if c.filled)


def query_from_wire(payload: Any) -> TicketQuery:
    """Build a :class:`TicketQuery` from a parsed request body.

    Tolerant by design: this runs *before* :func:`validate`, so anything missing
    or mistyped becomes a value validation can report rather than an exception
    that turns a bad clause into a 500.
    """
    raw = payload if isinstance(payload, dict) else {}
    clauses: list[QueryClause] = []
    for entry in raw.get("clauses") or []:
        if not isinstance(entry, dict):
            continue
        values = entry.get("values")
        if isinstance(values, str):
            values = [values]
        clauses.append(
            QueryClause(
                field=str(entry.get("field", "")),
                operator=str(entry.get("operator", "")),
                values=tuple(str(v) for v in (values or [])),
            )
        )
    sort_raw = raw.get("sort") if isinstance(raw.get("sort"), dict) else {}
    return TicketQuery(
        clauses=tuple(clauses),
        match=str(raw.get("match", "all")),
        sort=QuerySort(
            field=str((sort_raw or {}).get("field", "changedDate")),
            direction=str((sort_raw or {}).get("direction", "desc")),
        ),
    )


# ───────────────────────────────────────────────────────────────── validation

@dataclass(frozen=True)
class QueryProblem:
    """One thing wrong with a query.

    ``clause_index`` is what lets the UI print the message under the offending
    row. `dev-assistant` encoded that position in the message text (``Condition
    3: …``) and re-parsed it on the client; carrying it as a field instead means
    the client never has to parse a sentence to lay out a form.
    """

    message: str
    clause_index: int | None = None

    def as_dict(self) -> dict[str, Any]:
        return {"message": self.message, "clauseIndex": self.clause_index}


def _phrase(values: tuple[str, ...] | list[str]) -> str:
    """``a, b or c`` — for listing the operators a field does allow."""
    items = list(values)
    if len(items) <= 1:
        return items[0] if items else ""
    return f"{', '.join(items[:-1])} or {items[-1]}"


def validate(query: TicketQuery, destination: str) -> list[QueryProblem]:
    """Every problem with ``query`` for ``destination``; empty means valid.

    The client calls this to disable Apply before anything is sent; the API calls
    the same function to refuse a request that the client did not build. One
    definition, both sides — or the two disagree and "Apply is greyed out" stops
    matching "400 Bad Request".

    Never raises. The input can be any shape, so an unknown field or operator is
    *reported*, never assumed away.
    """
    problems: list[QueryProblem] = []

    if destination not in CAPABILITIES:
        problems.append(QueryProblem(f"“{destination}” is not somewhere a query can run."))
        return problems

    if not query.clauses:
        problems.append(QueryProblem("Add at least one condition."))

    if query.match not in ("all", "any"):
        problems.append(
            QueryProblem(f"“{query.match}” is not a way to combine conditions.")
        )

    for index, clause in enumerate(query.clauses):
        allowed = operators_for(destination, clause.field)
        label = FIELD_LABELS.get(clause.field, clause.field)

        if not allowed:
            known = clause.field in FIELD_LABELS
            problems.append(
                QueryProblem(
                    f"{label} cannot be filtered on this provider."
                    if known
                    else f"“{clause.field}” is not a field that can be filtered.",
                    index,
                )
            )
            continue

        if clause.operator not in allowed:
            readable = OPERATOR_LABELS.get(clause.operator, clause.operator)
            options = _phrase([OPERATOR_LABELS.get(op, op) for op in allowed])
            problems.append(
                QueryProblem(
                    f"{label} cannot be filtered with “{readable}”. Use {options}.",
                    index,
                )
            )
            continue

        if not clause.values:
            problems.append(QueryProblem(f"Give {label} a value.", index))
        elif any(v.strip() == "" for v in clause.values):
            problems.append(QueryProblem(f"One of the {label} values is empty.", index))

        if clause.operator not in LIST_OPERATORS and len(clause.values) > 1:
            readable = OPERATOR_LABELS.get(clause.operator, clause.operator)
            problems.append(
                QueryProblem(
                    f"“{readable}” takes one value, not {len(clause.values)}. "
                    "Use “is any of” for several.",
                    index,
                )
            )

    if query.sort.field not in SORT_FIELDS:
        problems.append(QueryProblem(f"“{query.sort.field}” is not a field to sort on."))
    if query.sort.direction not in SORT_DIRECTIONS:
        problems.append(
            QueryProblem(f"“{query.sort.direction}” is not a sort direction.")
        )

    return problems


def describe(query: TicketQuery) -> str:
    """The query as a person would say it — ``assigned to me · sprint under …``.

    Used for the "you are about to import" line and, later, as the stored
    description of a saved query. Deliberately lossy: it is prose, never
    something to compile back from.
    """
    parts: list[str] = []
    for clause in query.effective_clauses:
        label = FIELD_LABELS.get(clause.field, clause.field)
        operator = OPERATOR_LABELS.get(clause.operator, clause.operator)
        values = _phrase(clause.filled)
        parts.append(f"{label} {operator} {values}")
    if not parts:
        return "everything in the project"
    joiner = " · " if query.match == "all" else " or "
    return joiner.join(parts)
