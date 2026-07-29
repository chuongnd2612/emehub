"""``PATCH /projects/{key}/repos/{repo}/knowledge`` — the merge rule.

INTEGRATION.md §3 states the contract in one clause: the write path
"must not clobber existing ``verified_at_runtime`` entries". This file is that
clause, exercised from both sides — the service function directly, and the
endpoint an agent actually calls.

The rule, ported from QAgent's ``merge_verified_discovery``:

1. dedup by ``path`` (routes) / ``selector`` (selectors);
2. a colliding entry that is **already runtime-verified is left alone** and the
   incoming one is dropped;
3. a colliding entry that is **unverified** is upgraded in place, keeping its
   other keys;
4. anything new is appended;
5. merged and upgraded entries are stamped ``verified_at_runtime`` + ``source``.
"""

from __future__ import annotations

import pytest

from app.config import AUDIENCE_QAGENT
from app.models.knowledge import ProjectKnowledge, compose_key
from app.services import knowledge_service

PASSWORD = "password12345"
VERIFIED_EARLIER = "2026-01-01T00:00:00+00:00"


@pytest.fixture
def agent_headers(login):
    def _headers(email: str, password: str = PASSWORD):
        return {
            "Authorization": f"Bearer {login(email, password)['tokens'][AUDIENCE_QAGENT]}"
        }

    return _headers


@pytest.fixture
def alice(make_user):
    return make_user("alice@emesoft.net", PASSWORD)


@pytest.fixture
def bob(make_user):
    return make_user("bob@emesoft.net", PASSWORD)


@pytest.fixture
def admin(make_user):
    return make_user("admin@emesoft.net", PASSWORD, role="admin")


def _row(db, owner_id, knowledge=None, project_key="shop", repo="web"):
    row = ProjectKnowledge(
        key=compose_key(project_key, repo),
        project_key=project_key,
        repo=repo,
        name=project_key,
        owner_id=owner_id,
        knowledge=knowledge or {},
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _patch(client, headers, **body):
    response = client.patch(
        "/projects/shop/repos/web/knowledge", json=body, headers=headers
    )
    assert response.status_code == 200, response.text
    return response.json()


# ------------------------------------------------------- the no-clobber rule
def test_an_incoming_entry_never_overwrites_a_verified_selector(db_session, alice):
    """The headline guarantee. A runtime-verified selector survives a colliding
    discovery **unchanged** — value, strategy, source and timestamp."""
    row = _row(
        db_session,
        alice.id,
        {
            "selectors": [
                {
                    "screen": "login",
                    "element": "submit",
                    "selector": "#login-submit",
                    "strategy": "css",
                    "source": "exploration",
                    "verified_at_runtime": VERIFIED_EARLIER,
                }
            ]
        },
    )

    merged = knowledge_service.merge_discovery(
        row,
        {
            "selectors": [
                {
                    "screen": "login",
                    "element": "SIGN IN",
                    "selector": "#login-submit",
                    "strategy": "role",
                }
            ]
        },
        source="dom-heal",
    )

    assert merged == 0
    entry = row.knowledge["selectors"][0]
    assert entry["verified_at_runtime"] == VERIFIED_EARLIER
    assert entry["strategy"] == "css"
    assert entry["source"] == "exploration"
    assert entry["element"] == "submit"


def test_an_incoming_entry_never_overwrites_a_verified_route(db_session, alice):
    row = _row(
        db_session,
        alice.id,
        {
            "routes": [
                {
                    "path": "/checkout",
                    "description": "Checkout",
                    "auth_required": True,
                    "verified_at_runtime": VERIFIED_EARLIER,
                    "source": "exploration",
                }
            ]
        },
    )

    merged = knowledge_service.merge_discovery(
        row,
        {"routes": [{"path": "/checkout", "description": "WRONG", "auth_required": False}]},
        source="dom-heal",
    )

    assert merged == 0
    route = row.knowledge["routes"][0]
    assert route["description"] == "Checkout"
    assert route["auth_required"] is True
    assert route["verified_at_runtime"] == VERIFIED_EARLIER


def test_an_unverified_entry_is_upgraded_in_place_keeping_its_other_keys(db_session, alice):
    """A source-inferred entry is exactly what a runtime observation should
    improve — but the upgrade must not lose the fields the discovery omitted."""
    row = _row(
        db_session,
        alice.id,
        {
            "selectors": [
                {
                    "screen": "login",
                    "element": "submit",
                    "selector": "#login-submit",
                    "note": "inferred from source",
                }
            ]
        },
    )

    merged = knowledge_service.merge_discovery(
        row, {"selectors": [{"selector": "#login-submit", "strategy": "role"}]}
    )

    assert merged == 1
    assert len(row.knowledge["selectors"]) == 1
    entry = row.knowledge["selectors"][0]
    assert entry["note"] == "inferred from source"  # preserved
    assert entry["screen"] == "login"  # preserved
    assert entry["strategy"] == "role"  # upgraded
    assert entry["source"] == "exploration"
    assert entry["verified_at_runtime"]


def test_a_verified_entry_survives_alongside_new_ones(db_session, alice):
    """The mixed case: one collision with a verified entry (dropped) plus one
    genuinely new entry (appended) counts as exactly one merge."""
    row = _row(
        db_session,
        alice.id,
        {
            "selectors": [
                {"selector": "#keep-me", "verified_at_runtime": VERIFIED_EARLIER, "note": "gold"}
            ]
        },
    )

    merged = knowledge_service.merge_discovery(
        row,
        {
            "selectors": [
                {"selector": "#keep-me", "note": "overwrite attempt"},
                {"screen": "cart", "element": "qty", "selector": "[data-testid='qty']"},
            ]
        },
    )

    assert merged == 1
    by_selector = {s["selector"]: s for s in row.knowledge["selectors"]}
    assert by_selector["#keep-me"]["note"] == "gold"
    assert by_selector["[data-testid='qty']"]["verified_at_runtime"]


def test_new_entries_are_appended_and_stamped(db_session, alice):
    row = _row(db_session, alice.id, {})
    merged = knowledge_service.merge_discovery(
        row,
        {
            "routes": [{"path": "/cart"}],
            "selectors": [{"screen": "cart", "element": "qty", "selector": "#qty"}],
        },
        source="exploration",
    )

    assert merged == 2
    route = row.knowledge["routes"][0]
    selector = row.knowledge["selectors"][0]
    assert route["path"] == "/cart"
    assert route["source"] == "exploration"
    assert route["verified_at_runtime"]
    # Selectors additionally carry the strategy that worked, defaulting to css.
    assert selector["strategy"] == "css"
    assert selector["verified_at_runtime"]


def test_values_are_trimmed_and_deduped_against_the_untrimmed_form(db_session, alice):
    row = _row(db_session, alice.id, {"routes": [{"path": "/cart"}]})
    assert knowledge_service.merge_discovery(row, {"routes": [{"path": "  /cart  "}]}) == 1
    assert len(row.knowledge["routes"]) == 1


def test_blank_and_malformed_entries_are_ignored(db_session, alice):
    row = _row(db_session, alice.id, {})
    merged = knowledge_service.merge_discovery(
        row,
        {
            "routes": [{"path": "   "}, {"description": "no path"}, "not-a-dict"],
            "selectors": [{"selector": ""}, 42],
        },
    )
    assert merged == 0
    assert row.knowledge == {}


def test_an_empty_discovery_changes_nothing(db_session, alice):
    row = _row(db_session, alice.id, {"routes": [{"path": "/cart"}]})
    assert knowledge_service.merge_discovery(row, {}) == 0
    assert row.knowledge["routes"] == [{"path": "/cart"}]


def test_repeated_merges_are_idempotent_after_the_first(db_session, alice):
    """Once a discovery has been recorded it is verified, so replaying it hits
    the no-clobber branch instead of duplicating or re-stamping."""
    row = _row(db_session, alice.id, {})
    discovery = {"selectors": [{"screen": "cart", "element": "qty", "selector": "#qty"}]}

    assert knowledge_service.merge_discovery(row, discovery) == 1
    stamped = row.knowledge["selectors"][0]["verified_at_runtime"]
    assert knowledge_service.merge_discovery(row, discovery) == 0
    assert row.knowledge["selectors"][0]["verified_at_runtime"] == stamped
    assert len(row.knowledge["selectors"]) == 1


# --------------------------------------------------------------- the endpoint
def test_the_patch_endpoint_enforces_no_clobber(client, db_session, alice, agent_headers):
    _row(
        db_session,
        alice.id,
        {
            "selectors": [
                {
                    "selector": "#login-submit",
                    "strategy": "css",
                    "verified_at_runtime": VERIFIED_EARLIER,
                }
            ]
        },
    )

    body = _patch(
        client,
        agent_headers("alice@emesoft.net"),
        selectors=[{"selector": "#login-submit", "strategy": "xpath"}],
        source="dom-heal",
    )

    assert body["merged"] == 0
    entry = body["knowledge"]["knowledge"]["selectors"][0]
    assert entry["strategy"] == "css"
    assert entry["verified_at_runtime"] == VERIFIED_EARLIER


def test_the_patch_endpoint_merges_and_persists(client, db_session, alice, agent_headers):
    _row(db_session, alice.id, {})
    body = _patch(
        client,
        agent_headers("alice@emesoft.net"),
        routes=[{"path": "/cart", "description": "Cart"}],
        selectors=[{"screen": "cart", "element": "qty", "selector": "#qty"}],
    )
    assert body["merged"] == 2

    row = (
        db_session.query(ProjectKnowledge)
        .filter(
            ProjectKnowledge.key == compose_key("shop", "web"),
            ProjectKnowledge.owner_id == alice.id,
        )
        .one()
    )
    assert [r["path"] for r in row.knowledge["routes"]] == ["/cart"]
    assert row.knowledge["selectors"][0]["verified_at_runtime"]


def test_the_patch_endpoint_creates_the_row_on_demand(client, db_session, alice, agent_headers):
    """The hub cannot build a knowledge base itself, so a contribution must not
    be dropped merely because nothing has been indexed yet."""
    body = _patch(
        client, agent_headers("alice@emesoft.net"), routes=[{"path": "/cart"}]
    )
    assert body["merged"] == 1
    assert body["knowledge"]["status"] == "not_indexed"
    assert body["knowledge"]["shared"] is False

    row = (
        db_session.query(ProjectKnowledge)
        .filter(ProjectKnowledge.key == compose_key("shop", "web"))
        .one()
    )
    assert row.owner_id == alice.id
    assert row.project_key == "shop"
    assert row.repo == "web"


def test_a_member_cannot_merge_into_the_shared_knowledge(
    client, db_session, admin, alice, agent_headers
):
    """A member's contribution lands in their own namespace — the shared row
    everyone reads is untouched."""
    _row(db_session, None, {"routes": [{"path": "/home"}]})

    _patch(client, agent_headers("alice@emesoft.net"), routes=[{"path": "/cart"}])

    rows = {
        r.owner_id: [x["path"] for x in (r.knowledge.get("routes") or [])]
        for r in db_session.query(ProjectKnowledge)
        .filter(ProjectKnowledge.key == compose_key("shop", "web"))
        .all()
    }
    assert rows == {None: ["/home"], alice.id: ["/cart"]}


def test_an_admin_merges_into_the_shared_knowledge(client, db_session, admin, agent_headers):
    _row(db_session, None, {"routes": [{"path": "/home"}]})
    body = _patch(client, agent_headers("admin@emesoft.net"), routes=[{"path": "/cart"}])

    assert body["merged"] == 1
    assert body["knowledge"]["shared"] is True
    row = (
        db_session.query(ProjectKnowledge)
        .filter(ProjectKnowledge.key == compose_key("shop", "web"))
        .one()
    )
    assert sorted(r["path"] for r in row.knowledge["routes"]) == ["/cart", "/home"]


def test_a_merge_never_touches_another_members_row(
    client, db_session, alice, bob, agent_headers
):
    _row(db_session, bob.id, {"routes": [{"path": "/bob-only"}]})
    _patch(client, agent_headers("alice@emesoft.net"), routes=[{"path": "/cart"}])

    bob_row = (
        db_session.query(ProjectKnowledge)
        .filter(
            ProjectKnowledge.key == compose_key("shop", "web"),
            ProjectKnowledge.owner_id == bob.id,
        )
        .one()
    )
    assert [r["path"] for r in bob_row.knowledge["routes"]] == ["/bob-only"]


def test_a_merge_is_audited_without_leaking_the_payload(
    client, db_session, alice, agent_headers, auth_headers
):
    _patch(
        client,
        agent_headers("alice@emesoft.net"),
        selectors=[{"selector": "[data-testid='secret-field']"}],
    )
    events = client.get(
        "/audit/events", headers=auth_headers("alice@emesoft.net", PASSWORD)
    ).json()
    merged_events = [e for e in events if e["category"] == "knowledge"]
    assert merged_events, events
    event = merged_events[0]
    assert event["action"] == "Contributed runtime-verified knowledge"
    assert event["source"] == AUDIENCE_QAGENT
    assert event["target"] == "shop::web"
    assert "secret-field" not in event["meta"]
