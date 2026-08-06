"""Compile a :class:`~app.services.ticket_query.TicketQuery` into a GitHub search.

The third compiler, and the one where the destination genuinely cannot express what
the other two can. GitHub's issue search takes **qualifiers**, not a query language,
so this module's main job is being honest about the difference rather than
pretending it away.

## What GitHub cannot do, and why the matrix says so

* **No OR between qualifiers.** Every qualifier in a search string is ANDed, full
  stop. There is no grouping and no operator. So a ``match: "any"`` query is
  *refused* for this destination (``ticket_query.validate``) rather than quietly
  compiled as AND — which would return **fewer** tickets than asked for, silently.
* **No area path, no sprint, no parent, no priority, no epic.** GitHub issues have
  none of these concepts. They are absent from the capability matrix, so the UI
  never offers them.
* **Repeated qualifiers AND, they do not OR.** ``label:a label:b`` means *both*
  labels. The OR form is one qualifier with a comma: ``label:a,b``. Getting this
  backwards is the kind of bug that reads as "the filter found nothing" — so
  :func:`clause_to_qualifiers` emits the comma form for ``in`` and never repeats.

## The escaping, and why it removes rather than escapes

**GitHub's search syntax has no escape mechanism.** A value with a space is wrapped
in double quotes, and there is no way to put a double quote *inside* one. So a quote
in a value is **removed**, along with newlines — removal is the only choice that
cannot change which qualifier a value lands in. Everything else about the value is
passed through: search terms are matched, not executed, and GitHub is not a database
being asked to run them.

## Where "work item type" comes from

GitHub has no type field. The adapter *derives* one from labels when it normalises
an issue (``bug`` → Bug, ``enhancement``/``feature`` → Feature, ``epic`` → Epic), so
filtering by type has to use the same convention or the filter and the rows it
returns would disagree about what a Bug is. That symmetry is the argument for the
mapping below, not a guess about anyone's labelling.
"""

from __future__ import annotations

import re

from app.services.ticket_query import TicketQuery, resolve_date_macro

#: A value with any of these has to be quoted to stay one qualifier value.
_NEEDS_QUOTING = re.compile(r"[\s,]")

#: Removed, not escaped — see the module docstring. There is nowhere to put an
#: escape character in GitHub's search syntax.
_UNREPRESENTABLE = re.compile(r'["\r\n]')

#: The states GitHub actually has. A mirror-flavoured value like ``Done`` is mapped
#: onto one of them rather than sent as-is, because ``state:Done`` matches nothing
#: and would read as "there is no work" instead of "GitHub has two states".
_CLOSED_WORDS = frozenset({"closed", "done", "completed", "resolved", "fixed"})

#: Work item type → the label the adapter's own normaliser reads it back from.
_TYPE_LABELS: dict[str, str] = {
    "bug": "bug",
    "feature": "enhancement",
    "enhancement": "enhancement",
    "epic": "epic",
}

SORT_FIELDS: dict[str, str] = {
    "changedDate": "updated",
    "createdDate": "created",
    "id": "created",
    "state": "updated",
}


def sanitize(value: str) -> str:
    """A value with everything GitHub cannot represent taken out."""
    return _UNREPRESENTABLE.sub("", value).strip()


def literal(value: str) -> str:
    """A qualifier value: quoted when it would otherwise split into two."""
    cleaned = sanitize(value)
    if not cleaned:
        return ""
    return f'"{cleaned}"' if _NEEDS_QUOTING.search(cleaned) else cleaned


def state_for(value: str) -> str:
    """``open`` or ``closed`` — the only two an issue can be in."""
    return "closed" if sanitize(value).lower() in _CLOSED_WORDS else "open"


def login_for(value: str) -> str:
    """A login, or GitHub's own ``@me`` for the neutral ``@Me`` macro.

    From the table of one, never echoed: the macro is recognised by an exact match
    and the output is the constant below it.
    """
    cleaned = sanitize(value)
    return "@me" if cleaned.lower() == "@me" else literal(cleaned)


def date_for(value: str) -> str:
    """A date qualifier operand. Macros are resolved **here**, unlike the others.

    Azure DevOps and Jira expand ``@Today - 7`` themselves; GitHub does not, so the
    compiler has to. Same reason the mirror resolves them (see
    ``ticket_query.resolve_for_mirror``): a destination that cannot expand a macro
    must not be handed one, or it compares against the literal text and matches
    nothing.
    """
    resolved = resolve_date_macro(value)
    return sanitize(resolved if resolved is not None else value)


def clause_to_qualifiers(field: str, operator: str, values: tuple[str, ...]) -> list[str]:
    """One clause as zero or more search qualifiers.

    A list rather than a string because ``title contains`` produces two terms — the
    search word and ``in:title`` — and because a clause GitHub cannot express
    produces none. Negation is GitHub's ``-`` prefix, which works on qualifiers but
    not on bare search terms; the matrix accordingly offers ``contains`` on
    ``title`` and not ``notContains``.
    """
    filled = [v for v in values if v.strip() != ""]
    if not filled:
        return []
    first = filled[0]
    negate = operator in ("isNot", "notIn", "notContains")
    sign = "-" if negate else ""

    if field == "state":
        # `-state:open` is not a thing GitHub accepts, and it does not need to be:
        # an issue has exactly two states, so "not closed" *is* "open".
        state = state_for(first)
        if negate:
            state = "open" if state == "closed" else "closed"
        return [f"state:{state}"]

    if field == "assignee":
        who = login_for(first)
        return [f"{sign}assignee:{who}"] if who else []

    if field == "tags":
        # The comma form is GitHub's OR. Repeating `label:` would AND them, which is
        # the opposite of what `in` means.
        joined = ",".join(sanitize(v) for v in filled if sanitize(v))
        if not joined:
            return []
        quoted = f'"{joined}"' if _NEEDS_QUOTING.search(joined.replace(",", "")) else joined
        return [f"{sign}label:{quoted}"]

    if field == "workItemType":
        label = _TYPE_LABELS.get(sanitize(first).lower())
        # An unmapped type has no label convention to stand on. Emitting nothing
        # would silently widen the search, so emit a label of the type's own name
        # and let it match whoever uses that label.
        return [f"{sign}label:{literal(label or first)}"]

    if field == "title":
        term = literal(first)
        return [term, "in:title"] if term else []

    if field in ("changedSince", "createdSince"):
        key = "updated" if field == "changedSince" else "created"
        when = date_for(first)
        if not when:
            return []
        comparator = ">=" if operator == "onOrAfter" else "<="
        return [f"{key}:{comparator}{when}"]

    return []


def build_search(query: TicketQuery, *, org: str, repo: str) -> str:
    """The full ``q`` for ``GET /search/issues``.

    ``repo:`` and ``is:issue`` lead every search: the first scopes it to the
    connected repository — the same role ``[System.TeamProject]`` plays in WIQL,
    and safe here because every qualifier ANDs so nothing can widen past it — and
    the second keeps pull requests out, which the issues endpoint would otherwise
    include.
    """
    parts: list[str] = []
    if org and repo:
        parts.append(f"repo:{sanitize(org)}/{sanitize(repo)}")
    parts.append("is:issue")

    for clause in query.effective_clauses:
        parts.extend(
            part
            for part in clause_to_qualifiers(clause.field, clause.operator, clause.values)
            if part
        )

    # `in:title` is a scope for the search terms, not a filter, so one is enough
    # however many title clauses there were.
    seen_in_title = False
    deduped: list[str] = []
    for part in parts:
        if part == "in:title":
            if seen_in_title:
                continue
            seen_in_title = True
        deduped.append(part)
    return " ".join(deduped)


def sort_params(query: TicketQuery) -> dict[str, str]:
    """``sort``/``order`` for the search request.

    Separate from the ``q`` because GitHub takes them as their own parameters. ``id``
    has no qualifier of its own, so it falls back to creation order, which is the
    same thing for issues.
    """
    return {
        "sort": SORT_FIELDS.get(query.sort.field, "updated"),
        "order": "asc" if query.sort.direction == "asc" else "desc",
    }


__all__ = [
    "build_search",
    "clause_to_qualifiers",
    "date_for",
    "literal",
    "login_for",
    "sanitize",
    "sort_params",
    "state_for",
]
