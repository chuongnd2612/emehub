"""The clause model, the capability matrix, the validator and the mirror compiler.

Two properties carry most of the weight here.

**The matrix is the honesty mechanism.** A single query builder across three
providers only works if the UI is told what each provider cannot do. A clause the
destination cannot express must be *refused*, never accepted and dropped — a
dropped clause returns MORE tickets than were asked for, which is the worst way for
a filter to fail.

**The compiler and the matrix must not drift.** The mirror advertises the fields it
can filter on; if `_QUERY_COLUMNS` lacks one of them the clause compiles to nothing
and the UI has offered a control that does nothing.
"""

from __future__ import annotations

import pytest

from app.services import ticket_query as tq
from app.services import ticket_service


def clause(field: str, operator: str, *values: str) -> tq.QueryClause:
    return tq.QueryClause(field=field, operator=operator, values=tuple(values))


def query(*clauses: tq.QueryClause, match: str = "all", **sort) -> tq.TicketQuery:
    return tq.TicketQuery(
        clauses=tuple(clauses),
        match=match,
        sort=tq.QuerySort(**sort) if sort else tq.QuerySort(),
    )


# ─────────────────────────────────────────────────────── the capability matrix
def test_azure_devops_is_the_full_surface():
    """WIQL can express every field and operator, so the matrix must too."""
    fields = set(tq.fields_for("azure_devops"))
    assert "areaPath" in fields
    assert "parentId" in fields
    assert set(tq.operators_for("azure_devops", "areaPath")) == {"under", "is", "isNot"}
    assert set(tq.operators_for("azure_devops", "changedSince")) == {"onOrAfter", "onOrBefore"}


def test_paths_lead_with_under():
    """`=` on an area path silently excludes every child area, which is almost
    never what was meant — so `under` is offered first."""
    for destination in ("azure_devops", "mirror"):
        assert tq.operators_for(destination, "areaPath")[0] == "under"


def test_jira_has_no_area_path_tree():
    """JQL has no area-path concept, so the field is absent rather than present
    and ignored."""
    assert tq.operators_for("jira", "areaPath") == ()
    assert "areaPath" not in tq.fields_for("jira")


def test_github_offers_far_less_and_says_so():
    """The GitHub search API has qualifiers, not a query language. Pretending
    otherwise is what this matrix exists to prevent."""
    fields = set(tq.fields_for("github"))
    assert fields.isdisjoint({"areaPath", "iterationPath", "parentId", "priority", "epic"})
    assert set(tq.operators_for("github", "state")) == {"is", "isNot"}
    assert tq.operators_for("github", "title") == ("contains",)


def test_the_mirror_can_filter_everything_it_advertises():
    """The matrix and the compiler must not drift: every field the mirror offers
    needs a column, or the UI offers a control that does nothing."""
    advertised = set(tq.fields_for("mirror"))
    compilable = set(ticket_service._QUERY_COLUMNS)
    assert advertised - compilable == set(), advertised - compilable


# ────────────────────────────────────────────────────────────────── validation
def test_a_valid_query_has_no_problems():
    spec = query(clause("state", "in", "Active", "New"))
    assert tq.validate(spec, "azure_devops") == []


def test_an_empty_query_asks_for_a_condition():
    problems = tq.validate(query(), "azure_devops")
    assert any(p.message == "Add at least one condition." for p in problems)


def test_an_unknown_field_is_reported_not_assumed_away():
    """The input arrives from an HTTP body, so every lookup must survive a key
    that is not in the table."""
    problems = tq.validate(query(clause("nonsense", "is", "x")), "azure_devops")
    assert len(problems) == 1
    assert "is not a field that can be filtered" in problems[0].message
    assert problems[0].clause_index == 0


def test_a_field_the_provider_lacks_is_refused_per_provider():
    spec = query(clause("areaPath", "under", "Surency"))
    assert tq.validate(spec, "azure_devops") == []
    problems = tq.validate(spec, "jira")
    assert len(problems) == 1
    assert "cannot be filtered on this provider" in problems[0].message
    assert problems[0].clause_index == 0


def test_a_disallowed_operator_names_the_ones_that_work():
    problems = tq.validate(query(clause("state", "under", "Active")), "azure_devops")
    assert len(problems) == 1
    assert "cannot be filtered with" in problems[0].message
    # The message has to be actionable, not just a refusal.
    assert "is any of" in problems[0].message


def test_a_single_value_operator_refuses_several_values():
    problems = tq.validate(query(clause("state", "is", "Active", "New")), "azure_devops")
    assert any("takes one value, not 2" in p.message for p in problems)
    assert any("is any of" in p.message for p in problems)


@pytest.mark.parametrize(
    ("values", "fragment"),
    [
        # An untouched control — no values, or every one of them blank — asks for
        # a value. Reporting an "empty value" there reads as a mistake the user
        # made rather than one they have yet to make.
        ((), "Give state a value."),
        (("",), "Give state a value."),
        (("   ",), "Give state a value."),
        # A blank *among* real ones is a different thing, and says so.
        (("Active", ""), "One of the state values is empty."),
    ],
)
def test_missing_and_blank_values_are_both_caught(values, fragment):
    spec = query(tq.QueryClause(field="state", operator="in", values=values))
    assert any(fragment in p.message for p in tq.validate(spec, "azure_devops"))


def test_bad_match_and_sort_are_caught():
    spec = tq.TicketQuery(
        clauses=(clause("state", "is", "Active"),),
        match="either",
        sort=tq.QuerySort(field="whenever", direction="sideways"),
    )
    messages = " ".join(p.message for p in tq.validate(spec, "azure_devops"))
    assert "not a way to combine conditions" in messages
    assert "not a field to sort on" in messages
    assert "not a sort direction" in messages


def test_an_unknown_destination_is_refused_before_anything_else():
    problems = tq.validate(query(clause("state", "is", "Active")), "gitlab")
    assert len(problems) == 1
    assert "not somewhere a query can run" in problems[0].message


def test_the_clause_index_places_the_message():
    """The UI prints each message under its own row, so position travels as a
    field rather than being parsed back out of the sentence."""
    spec = query(
        clause("state", "is", "Active"),
        clause("state", "under", "nope"),
    )
    problems = tq.validate(spec, "azure_devops")
    assert [p.clause_index for p in problems] == [1]


# ───────────────────────────────────────────────────────────── the wire shape
def test_a_hostile_body_becomes_reportable_values_not_an_exception():
    """`query_from_wire` runs before validation, so anything mistyped has to
    survive as a value the validator can complain about."""
    spec = tq.query_from_wire(
        {"clauses": [{"field": 1, "operator": None}, "not-a-clause"], "sort": "nope"}
    )
    assert len(spec.clauses) == 1
    assert spec.clauses[0].field == "1"
    assert spec.sort.field == "changedDate"
    assert tq.validate(spec, "azure_devops")


def test_a_string_value_is_accepted_as_one_value():
    spec = tq.query_from_wire({"clauses": [{"field": "state", "operator": "is", "values": "Active"}]})
    assert spec.clauses[0].values == ("Active",)


def test_blank_clauses_are_inert():
    """A half-typed clause must not compile to `field = ''`, which matches nothing
    and reads as "there is no work" rather than as unfinished input."""
    spec = query(clause("state", "is", "  "), clause("title", "contains", "boom"))
    assert len(spec.effective_clauses) == 1
    assert spec.effective_clauses[0].field == "title"


def test_describe_reads_as_a_sentence():
    spec = query(clause("assignee", "is", "@Me"), clause("state", "in", "Active", "New"))
    assert tq.describe(spec) == "assigned to is @Me · state is any of Active or New"
    assert tq.describe(query(clause("state", "in", "A", "B"), match="any")).startswith("state")
    assert tq.describe(query()) == "everything in the project"


# ──────────────────────────────────────────────────── the mirror compiler
@pytest.fixture
def rows(db_session, make_user):
    """A small spread to filter over."""
    from app.models.ticket import Ticket

    owner = make_user("qb-owner@emesoft.net", "password12345")
    made = []
    for external_id, kind, status, area, sprint, title, labels in [
        ("SUR-1", "Bug", "Active", "Surency\\Data", "Sprint 1", "Import fails", ["backend"]),
        ("SUR-2", "User Story", "New", "Surency\\Data\\Ingest", "Sprint 1", "Add mapping", ["ui"]),
        ("SUR-3", "Bug", "Closed", "Surency\\Web", "Sprint 2", "Fix banner", ["ui", "urgent"]),
    ]:
        ticket = Ticket(
            external_id=external_id,
            provider_kind="ado",
            owner_id=owner.id,
            work_item_type=kind,
            status=status,
            area_path=area,
            sprint=sprint,
            title=title,
            labels=labels,
            assignee="duna",
            priority="High",
        )
        db_session.add(ticket)
        made.append(ticket)
    db_session.commit()
    return owner, made


def ids(db_session, owner, spec):
    items, _ = ticket_service.list_tickets(db_session, owner, spec=spec)
    return sorted(t.external_id for t in items)


def test_is_and_is_not(db_session, rows):
    owner, _ = rows
    assert ids(db_session, owner, query(clause("state", "is", "Active"))) == ["SUR-1"]
    assert ids(db_session, owner, query(clause("state", "isNot", "Active"))) == ["SUR-2", "SUR-3"]


def test_in_and_not_in(db_session, rows):
    owner, _ = rows
    assert ids(db_session, owner, query(clause("state", "in", "Active", "New"))) == ["SUR-1", "SUR-2"]
    assert ids(db_session, owner, query(clause("state", "notIn", "Active", "New"))) == ["SUR-3"]


def test_contains_and_not_contains(db_session, rows):
    owner, _ = rows
    assert ids(db_session, owner, query(clause("title", "contains", "fail"))) == ["SUR-1"]
    assert ids(db_session, owner, query(clause("title", "notContains", "fail"))) == ["SUR-2", "SUR-3"]


def test_under_includes_children(db_session, rows):
    """The whole reason paths lead with `under`: `=` would drop SUR-2."""
    owner, _ = rows
    assert ids(db_session, owner, query(clause("areaPath", "under", "Surency\\Data"))) == [
        "SUR-1",
        "SUR-2",
    ]
    assert ids(db_session, owner, query(clause("areaPath", "is", "Surency\\Data"))) == ["SUR-1"]


def test_tags_match_inside_the_json_list(db_session, rows):
    owner, _ = rows
    assert ids(db_session, owner, query(clause("tags", "contains", "urgent"))) == ["SUR-3"]


def test_match_all_narrows_and_match_any_widens(db_session, rows):
    owner, _ = rows
    both = (clause("state", "is", "Active"), clause("workItemType", "is", "User Story"))
    assert ids(db_session, owner, query(*both, match="all")) == []
    assert ids(db_session, owner, query(*both, match="any")) == ["SUR-1", "SUR-2"]


def test_an_or_query_still_cannot_see_another_members_tickets(
    db_session, rows, make_user
):
    """`match: any` widens within the visible set and never past it."""
    from app.models.ticket import Ticket

    other = make_user("qb-other@emesoft.net", "password12345")
    db_session.add(
        Ticket(
            external_id="SECRET-1",
            provider_kind="ado",
            owner_id=other.id,
            status="Active",
            title="Not yours",
            labels=[],
        )
    )
    db_session.commit()

    owner, _ = rows
    found = ids(
        db_session,
        owner,
        query(clause("state", "is", "Active"), clause("title", "contains", "Not yours"), match="any"),
    )
    assert "SECRET-1" not in found


def test_a_spec_composes_with_the_existing_kwargs(db_session, rows):
    """The pill filters and `GET /tickets`' own parameters keep working alongside
    a clause query — both narrow the same visible set."""
    owner, _ = rows
    items, _ = ticket_service.list_tickets(
        db_session,
        owner,
        work_item_types=["Bug"],
        spec=query(clause("state", "in", "Active", "Closed")),
    )
    assert sorted(t.external_id for t in items) == ["SUR-1", "SUR-3"]


def test_an_empty_spec_narrows_nothing(db_session, rows):
    owner, _ = rows
    assert ids(db_session, owner, query()) == ["SUR-1", "SUR-2", "SUR-3"]


# ─────────────────────────────────────────── the two halves must not drift
def test_the_typescript_matrix_matches_this_one():
    """The client validates to grey out Apply; the API validates to refuse a
    request. They are two files in two languages, so nothing but a test stops them
    disagreeing — and a disagreement means "Apply is disabled" stops matching
    "400 Bad Request".

    Parsed rather than imported, obviously; this asserts the *shape* the client
    offers, which is the part a user sees.
    """
    import re
    from pathlib import Path

    source = (
        Path(__file__).resolve().parents[2] / "app" / "src" / "data" / "ticketQuery.ts"
    ).read_text(encoding="utf-8")

    # Resolve the named operator sets the matrix is written in terms of.
    aliases = {
        "EQUALITY": ["is", "isNot", "in", "notIn"],
        "PATH": ["under", "is", "isNot"],
        "TEXT": ["contains", "notContains"],
        "DATE": ["onOrAfter", "onOrBefore"],
    }
    for name, expected in aliases.items():
        declared = re.search(rf"const {name}: ClauseOperator\[\] = \[(.*?)\];", source, re.S)
        assert declared, f"{name} is no longer declared as expected"
        assert re.findall(r'"(\w+)"', declared.group(1)) == expected, name

    block = re.search(
        r"export const CAPABILITIES:.*?= \{(.*?)\n\};", source, re.S
    )
    assert block, "CAPABILITIES is no longer parseable — update this test with it"

    parsed: dict[str, dict[str, list[str]]] = {}
    for destination, body in re.findall(r"(\w+): \{(.*?)\n  \},", block.group(1), re.S):
        entries: dict[str, list[str]] = {}
        for field, value in re.findall(r"(\w+): (\[[^\]]*\]|\w+),", body):
            entries[field] = (
                aliases[value] if value in aliases else re.findall(r'"(\w+)"', value)
            )
        parsed[destination] = entries

    expected = {
        destination: {field: list(ops) for field, ops in fields.items()}
        for destination, fields in tq.CAPABILITIES.items()
    }
    assert parsed == expected


# ────────────────────────────────────── the query over HTTP: preview and sync
class SpecSource:
    """A TicketSource that records the spec it was handed."""

    def __init__(self, items=None, total=None):
        self.items = items or [
            {"external_id": "SUR-1", "title": "One", "status": "Active"},
            {"external_id": "SUR-2", "title": "Two", "status": "New"},
        ]
        #: What the provider says the real total is, independently of how many
        #: rows a (capped) fetch returns.
        self.total = total
        self.seen: list = []
        self.counted: list = []

    def fetch_tickets(self, **selection):
        self.seen.append(selection)
        return self.items

    def count_tickets(self, **selection):
        """Uncapped, as a real provider's count is — see `total` below."""
        self.counted.append(selection)
        return self.total if self.total is not None else len(self.items)


def resolver_for(source):
    def _resolve(db, user, connection_id, provider_kind):
        return ticket_service.ResolvedSource(
            source=source,
            provider_kind=provider_kind or "azure_devops",
            connection_id=connection_id or 7,
            label="ADO",
        )

    return _resolve


VALID = {
    "clauses": [{"field": "state", "operator": "in", "values": ["Active", "New"]}],
    "match": "all",
    "sort": {"field": "changedDate", "direction": "desc"},
}


@pytest.fixture
def member(client, make_user, auth_headers):
    make_user("qb-http@emesoft.net", "password12345")
    return auth_headers("qb-http@emesoft.net", "password12345")


def test_preview_reports_the_total_without_importing(client, member, db_session):
    """The honest item count: the handoff's "~24 items" hints were deleted because
    nothing could count a provider-side scope without performing it."""
    from app.models.ticket import Ticket

    source = SpecSource()
    with ticket_service.use_ticket_source_resolver(resolver_for(source)):
        response = client.post(
            "/tickets/query/preview",
            json={"providerKind": "azure_devops", "query": VALID},
            headers=member,
        )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["total"] == 2
    assert [row["externalId"] for row in body["sample"]] == ["SUR-1", "SUR-2"]
    assert body["description"] == "state is any of Active or New"
    # Nothing was written.
    assert db_session.query(Ticket).count() == 0


def test_preview_hands_the_compiled_spec_to_the_adapter(client, member):
    source = SpecSource()
    with ticket_service.use_ticket_source_resolver(resolver_for(source)):
        client.post(
            "/tickets/query/preview",
            json={"providerKind": "azure_devops", "query": VALID},
            headers=member,
        )
    spec = source.seen[0]["spec"]
    assert spec.clauses[0].field == "state"
    assert spec.clauses[0].values == ("Active", "New")


def test_sync_with_a_query_imports_and_ignores_the_legacy_fields(client, member):
    """Blending the two would silently re-apply a condition the user removed."""
    source = SpecSource()
    with ticket_service.use_ticket_source_resolver(resolver_for(source)):
        response = client.post(
            "/tickets/sync",
            json={
                "providerKind": "azure_devops",
                "query": VALID,
                "mode": "sprint",
                "sprint": "Sprint 99",
            },
            headers=member,
        )
    assert response.status_code == 200, response.text
    assert response.json()["synced"] == 2
    assert source.seen[0]["spec"] is not None


def test_sync_without_a_query_is_untouched(client, member):
    """The legacy path is the bridge for agents already calling this route."""
    source = SpecSource()
    with ticket_service.use_ticket_source_resolver(resolver_for(source)):
        client.post(
            "/tickets/sync",
            json={"providerKind": "azure_devops", "mode": "assigned"},
            headers=member,
        )
    assert source.seen[0]["spec"] is None
    assert source.seen[0]["mode"] == "assigned"


def test_an_invalid_query_is_refused_with_the_problems_positioned(client, member):
    """The same validator the client greys out Apply with, so the two agree."""
    source = SpecSource()
    with ticket_service.use_ticket_source_resolver(resolver_for(source)):
        response = client.post(
            "/tickets/query/preview",
            json={
                "providerKind": "azure_devops",
                "query": {"clauses": [{"field": "state", "operator": "under", "values": ["x"]}]},
            },
            headers=member,
        )
    assert response.status_code == 422
    problems = response.json()["detail"]["problems"]
    assert problems[0]["clauseIndex"] == 0
    assert "cannot be filtered with" in problems[0]["message"]
    assert source.seen == [], "an invalid query must not reach the provider"


def test_a_query_for_a_field_the_provider_lacks_is_refused(client, member):
    source = SpecSource()
    with ticket_service.use_ticket_source_resolver(resolver_for(source)):
        response = client.post(
            "/tickets/query/preview",
            json={
                "providerKind": "github",
                "query": {"clauses": [{"field": "areaPath", "operator": "under", "values": ["x"]}]},
            },
            headers=member,
        )
    assert response.status_code == 422
    assert "cannot be filtered on this provider" in response.json()["detail"]["problems"][0]["message"]


def test_a_smuggled_wiql_key_is_refused(client, member):
    """extra="forbid" is what stops a raw query string riding in on the body."""
    response = client.post(
        "/tickets/query/preview",
        json={"providerKind": "azure_devops", "query": VALID, "wiql": "SELECT 1"},
        headers=member,
    )
    assert response.status_code == 422


def test_preview_requires_authentication(client):
    assert client.post("/tickets/query/preview", json={"query": VALID}).status_code == 401


def test_the_preview_total_is_the_real_count_not_the_capped_fetch(client, member):
    """`fetch_tickets` is capped at 200 so a bulk sync cannot hang. Reporting that
    number as the total would tell someone with 900 bugs they have 200 — silent
    truncation reading as the truth. The count comes from the uncapped id list."""
    source = SpecSource(total=873)
    with ticket_service.use_ticket_source_resolver(resolver_for(source)):
        response = client.post(
            "/tickets/query/preview",
            json={"providerKind": "azure_devops", "query": VALID},
            headers=member,
        )
    body = response.json()
    assert body["total"] == 873
    assert len(body["sample"]) == 2, "the sample stays short; only the total is real"
    assert source.counted, "the count must not be derived from the fetch"


# ─────────────────────────── the mirror over HTTP: POST /tickets/search
def test_search_narrows_the_mirror_by_clauses(client, member, db_session, make_user):
    from app.models.ticket import Ticket

    owner = make_user("qb-search@emesoft.net", "password12345")
    headers = None
    # The member fixture owns the rows it can see, so seed against that principal.
    from app.models.user import User

    principal = db_session.query(User).filter(User.email == "qb-http@emesoft.net").one()
    for external_id, kind, status in [
        ("S-1", "Bug", "Active"),
        ("S-2", "User Story", "Active"),
        ("S-3", "Bug", "Closed"),
    ]:
        db_session.add(
            Ticket(
                external_id=external_id,
                provider_kind="ado",
                owner_id=principal.id,
                work_item_type=kind,
                status=status,
                title=f"Row {external_id}",
                labels=[],
            )
        )
    db_session.commit()
    assert owner is not None and headers is None  # fixture noise, kept explicit

    response = client.post(
        "/tickets/search",
        json={
            "query": {
                "clauses": [
                    {"field": "workItemType", "operator": "is", "values": ["Bug"]},
                    {"field": "state", "operator": "is", "values": ["Active"]},
                ],
                "match": "all",
                "sort": {"field": "changedDate", "direction": "desc"},
            }
        },
        headers=member,
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert [row["externalId"] for row in body["items"]] == ["S-1"]
    assert body["total"] == 1


def test_search_refuses_a_clause_the_mirror_cannot_run(client, member):
    """`parentId` has no column here, so the matrix omits it for the mirror."""
    response = client.post(
        "/tickets/search",
        json={"query": {"clauses": [{"field": "parentId", "operator": "is", "values": ["7"]}]}},
        headers=member,
    )
    assert response.status_code == 422
    assert "cannot be filtered on this provider" in response.json()["detail"]["problems"][0]["message"]


def test_search_cannot_see_another_members_rows(client, member, db_session, make_user):
    """An `any` query widens within the visible set and never past it."""
    from app.models.ticket import Ticket

    other = make_user("qb-victim@emesoft.net", "password12345")
    db_session.add(
        Ticket(
            external_id="SECRET-7",
            provider_kind="ado",
            owner_id=other.id,
            status="Active",
            title="Not yours",
            labels=[],
        )
    )
    db_session.commit()

    response = client.post(
        "/tickets/search",
        json={
            "query": {
                "clauses": [
                    {"field": "state", "operator": "is", "values": ["Active"]},
                    {"field": "title", "operator": "contains", "values": ["Not yours"]},
                ],
                "match": "any",
            }
        },
        headers=member,
    )
    assert response.status_code == 200
    assert "SECRET-7" not in [row["externalId"] for row in response.json()["items"]]


def test_search_still_honours_the_free_text_and_paging(client, member, db_session):
    from app.models.ticket import Ticket
    from app.models.user import User

    principal = db_session.query(User).filter(User.email == "qb-http@emesoft.net").one()
    for n in range(6):
        db_session.add(
            Ticket(
                external_id=f"P-{n}",
                provider_kind="ado",
                owner_id=principal.id,
                status="Active",
                title="Pageable row",
                labels=[],
            )
        )
    db_session.commit()

    first = client.post(
        "/tickets/search",
        json={"query": {}, "q": "Pageable", "page": 1, "pageSize": 4},
        headers=member,
    ).json()
    assert len(first["items"]) == 4
    assert first["total"] == 6

    second = client.post(
        "/tickets/search",
        json={"query": {}, "q": "Pageable", "page": 2, "pageSize": 4},
        headers=member,
    ).json()
    assert len(second["items"]) == 2


def test_search_refuses_a_smuggled_sql_key(client, member):
    response = client.post(
        "/tickets/search",
        json={"query": {}, "where": "1=1"},
        headers=member,
    )
    assert response.status_code == 422
