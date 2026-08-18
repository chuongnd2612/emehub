"""The three views DAgent asks a project for, and where each is bounded.

Driven at the HTTP seam (``_client`` / ``_get`` are replaced), because what is
worth protecting is the *query* each scope builds and the *project* it is built
against — neither needs a live provider to observe, and both are the things that
silently answer the wrong question when they drift:

* a backlog and a board are not the sprint query with a filter. They are bounded
  differently at the provider, so a scope that leaked back to the iteration
  clause would answer with the current sprint under another name;
* the sprint scope must keep closed work (it is the record of what that sprint
  did) while the other two must drop it (they are lists of work to pick up);
* every one of them, and the sprint list beside them, is scoped by the
  **caller's** project. One connection spans an organisation, and resolving the
  project from the connection is what made the sprint picker disagree with the
  ticket list next to it.
"""

from __future__ import annotations

import pytest

from app.services import dagent_provider
from app.services.dagent_provider import ProviderUnavailable

ORG = "https://dev.azure.com/contoso"
CONNECTION_PROJECT = "Contoso"
OTHER_PROJECT = "Northwind"


class FakeClient:
    def __init__(self, sink: dict):
        self._sink = sink

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def post(self, path, params=None, json=None):
        self._sink["post_path"] = path
        self._sink["query"] = (json or {}).get("query", "")
        return FakeResponse({"workItems": [{"id": 7}]})


class FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


def _work_item(item_id: int = 7, **fields) -> dict:
    base = {
        "System.Id": item_id,
        "System.Title": "Add the thing",
        "System.WorkItemType": "User Story",
        "System.State": "Active",
        "System.IterationPath": f"{CONNECTION_PROJECT}\\Sprint 3",
    }
    base.update(fields)
    return {"id": item_id, "fields": base}


@pytest.fixture
def provider(monkeypatch):
    """``dagent_provider`` with the provider replaced, and a sink recording what
    it was asked. Returns ``(sink, install)``."""
    sink: dict = {"gets": []}

    def fake_get(client, path, pat, **params):
        sink["gets"].append((path, params))
        if "teamsettings/iterations" in path:
            return {"value": sink.get("iterations", [])}
        return {"value": [_work_item()]}

    monkeypatch.setattr(
        dagent_provider, "_ado_context", lambda conn: (ORG, CONNECTION_PROJECT, "pat")
    )
    monkeypatch.setattr(dagent_provider, "_client", lambda org, pat: FakeClient(sink))
    monkeypatch.setattr(dagent_provider, "_get", fake_get)
    return sink


# ------------------------------------------------------------------ scopes
def test_sprint_scope_is_bounded_by_the_current_iteration(provider):
    dagent_provider.list_tickets(object(), project=OTHER_PROJECT)
    assert "[System.IterationPath] = @currentIteration" in provider["query"]


def test_a_named_sprint_replaces_the_current_iteration(provider):
    dagent_provider.list_tickets(object(), project=OTHER_PROJECT, sprint="Northwind\\Sprint 9")
    assert "UNDER 'Northwind\\Sprint 9'" in provider["query"]
    assert "@currentIteration" not in provider["query"]


def test_a_rooted_path_costs_no_extra_lookup(provider):
    """The whole reason ``/sprints`` hands out ``path``: a caller that passes it
    back is already giving WIQL what it needs."""
    dagent_provider.list_tickets(object(), project=OTHER_PROJECT, sprint="Northwind\\Sprint 9")
    assert not any("teamsettings/iterations" in p for p, _ in provider["gets"])


def test_a_bare_sprint_name_is_resolved_to_its_real_path(provider):
    """The 400 this exists to stop. ``System.IterationPath`` is rooted, and ADO
    does not treat ``UNDER 'Sprint 9'`` as "matches nothing" — it rejects the
    whole query, so a caller that sends the name a picker displayed gets a 502
    describing a query it never wrote."""
    provider["iterations"] = [
        {
            "id": "b",
            "name": "Sprint 9",
            "path": "Northwind\\Release 1\\Sprint 9",
            "attributes": {"timeFrame": "current"},
        }
    ]
    dagent_provider.list_tickets(object(), project=OTHER_PROJECT, sprint="Sprint 9")
    # The nested path, not the flat guess — this is why the lookup is worth a call.
    assert "UNDER 'Northwind\\Release 1\\Sprint 9'" in provider["query"]


def test_an_unknown_bare_name_falls_back_to_the_flat_path(provider):
    """Right for the common flat layout, and an empty sprint is something a user
    can act on where a 502 about WIQL is not."""
    dagent_provider.list_tickets(object(), project=OTHER_PROJECT, sprint="Sprint 61")
    assert "UNDER 'Northwind\\Sprint 61'" in provider["query"]


def test_the_label_is_a_name_even_when_a_path_was_sent(provider):
    """A header chip is a name; ``Northwind\\Release 1\\Sprint 9`` is a location."""
    _, label, _ = dagent_provider.list_tickets(
        object(), project=OTHER_PROJECT, sprint="Northwind\\Release 1\\Sprint 9"
    )
    assert label == "Sprint 9"


def test_a_sprint_keeps_its_closed_work(provider):
    """A sprint is the record of what that iteration worked on. Dropping closed
    items would make a finished sprint look empty."""
    dagent_provider.list_tickets(object(), project=OTHER_PROJECT)
    assert "NOT IN" not in provider["query"]


def test_backlog_is_unscheduled_open_work(provider):
    dagent_provider.list_tickets(object(), project=OTHER_PROJECT, scope="backlog")
    query = provider["query"]
    # The iteration path still at the project root — an unassigned item inherits
    # it, which is what "not scheduled into a sprint yet" is in ADO.
    assert f"[System.IterationPath] = '{OTHER_PROJECT}'" in query
    assert "@currentIteration" not in query
    assert "[System.State] NOT IN ('Closed','Removed','Done')" in query


def test_board_spans_every_iteration(provider):
    """The reason board is not the sprint query with a filter: its cards live in
    iterations the sprint query is bounded away from."""
    dagent_provider.list_tickets(object(), project=OTHER_PROJECT, scope="board")
    query = provider["query"]
    assert "IterationPath" not in query
    assert "[System.State] NOT IN ('Closed','Removed','Done')" in query


def test_a_sprint_is_ignored_when_the_scope_is_not_the_sprint(provider):
    dagent_provider.list_tickets(
        object(), project=OTHER_PROJECT, sprint="Northwind\\Sprint 9", scope="board"
    )
    assert "Sprint 9" not in provider["query"]


def test_only_the_sprint_scope_claims_a_sprint_label(provider):
    """A backlog and a board span iterations, so naming one would be false — and
    the header renders whatever comes back."""
    _, sprint_label, _ = dagent_provider.list_tickets(object(), project=OTHER_PROJECT)
    assert sprint_label == "Sprint 3"

    for scope in ("backlog", "board"):
        _, label, _ = dagent_provider.list_tickets(object(), project=OTHER_PROJECT, scope=scope)
        assert label == "", scope


def test_the_board_column_survives_the_normalisation(provider, monkeypatch):
    """It is requested by name and it is not the state — a board maps several
    states onto one column."""
    monkeypatch.setattr(
        dagent_provider,
        "_get",
        lambda client, path, pat, **p: {
            "value": [_work_item(**{"System.BoardColumn": "In Review", "System.State": "Active"})]
        },
    )
    tickets, _, _ = dagent_provider.list_tickets(object(), project=OTHER_PROJECT, scope="board")
    assert tickets[0]["boardColumn"] == "In Review"
    assert tickets[0]["status"] == "Active"
    assert "System.BoardColumn" in dagent_provider._TICKET_FIELDS


def test_a_capped_list_says_so(provider, monkeypatch):
    """A sprint is bounded by its iteration; a backlog is not. A silently capped
    board would read as a short one."""
    monkeypatch.setattr(dagent_provider, "MAX_TICKETS", 1)

    class ManyClient(FakeClient):
        def post(self, path, params=None, json=None):
            self._sink["query"] = (json or {}).get("query", "")
            return FakeResponse({"workItems": [{"id": 7}, {"id": 8}, {"id": 9}]})

    monkeypatch.setattr(dagent_provider, "_client", lambda org, pat: ManyClient(provider))
    _, _, truncated = dagent_provider.list_tickets(object(), project=OTHER_PROJECT, scope="board")
    assert truncated is True

    monkeypatch.setattr(dagent_provider, "MAX_TICKETS", 200)
    _, _, truncated = dagent_provider.list_tickets(object(), project=OTHER_PROJECT, scope="board")
    assert truncated is False


def test_an_apostrophe_in_a_name_does_not_break_the_query(provider):
    dagent_provider.list_tickets(object(), project="O'Brien", sprint="O'Brien\\S 1")
    assert "'O''Brien'" in provider["query"]
    assert "UNDER 'O''Brien\\S 1'" in provider["query"]


# ------------------------------------------------------------------ sprints
def test_sprints_are_read_for_the_project_the_caller_named(provider):
    """Not the connection's. This is the bug the parameter exists to fix: the
    picker went empty (or answered for another project) while the ticket list
    beside it, which does take a project, kept working."""
    dagent_provider.list_sprints(object(), project=OTHER_PROJECT)
    paths = [p for p, _ in provider["gets"]]
    assert any(f"/{OTHER_PROJECT}/_apis/work/teamsettings/iterations" in p for p in paths)


def test_sprints_fall_back_to_the_connection_project(provider):
    dagent_provider.list_sprints(object())
    paths = [p for p, _ in provider["gets"]]
    assert any(f"/{CONNECTION_PROJECT}/_apis/work/teamsettings/iterations" in p for p in paths)


def test_sprints_with_no_project_anywhere_is_a_routing_gap(provider, monkeypatch):
    """404, not 502: no retry will make an unnamed project resolve."""
    monkeypatch.setattr(dagent_provider, "_ado_context", lambda conn: (ORG, "", "pat"))
    with pytest.raises(ProviderUnavailable):
        dagent_provider.list_sprints(object())


def test_sprints_are_the_team_s_list_not_the_project_s_iteration_tree(provider):
    """A sprint list has exactly one scope in ADO, and it is a team — its own URL
    is ``_sprints/backlog/<team>/…``. The project's iteration tree is every
    team's sprints at once, which is a list matching no screen a user has seen:
    ``CPCAG Sprint 75`` next to ``FM-Schwab-Egnyte\\Sprint 8`` next to
    ``Sprint 47``."""
    dagent_provider.list_sprints(object(), project=OTHER_PROJECT)
    paths = [p for p, _ in provider["gets"]]
    assert any(f"/{OTHER_PROJECT}/_apis/work/teamsettings/iterations" in p for p in paths)
    assert not any("classificationnodes" in p for p in paths)


def test_the_time_frame_is_the_provider_s_own_classification(provider):
    """Not a comparison of two dates against today: several sub-trees have a
    sprint spanning now, so dates cannot say which one is being worked. Team
    settings answers for one team, so exactly one is current."""
    provider["iterations"] = [
        {
            "id": "a",
            "name": "Sprint 64",
            "path": "Northwind\\Sprint 64",
            "attributes": {
                "startDate": "2026-07-01T00:00:00Z",
                "finishDate": "2026-07-14T00:00:00Z",
                "timeFrame": "past",
            },
        },
        {
            "id": "b",
            "name": "Sprint 65",
            "path": "Northwind\\Sprint 65",
            "attributes": {
                "startDate": "2026-08-01T00:00:00Z",
                "finishDate": "2026-08-14T00:00:00Z",
                "timeFrame": "current",
            },
        },
    ]
    rows = dagent_provider.list_sprints(object(), project=OTHER_PROJECT)
    assert [r["name"] for r in rows] == ["Sprint 64", "Sprint 65"]
    assert [r["time_frame"] for r in rows] == ["past", "current"]
    # Already rooted — this endpoint carries no structural "Iteration" segment.
    assert rows[1]["path"] == "Northwind\\Sprint 65"
    assert rows[1]["start_date"] == "2026-08-01T00:00:00Z"
