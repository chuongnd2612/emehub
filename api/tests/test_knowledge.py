"""Project knowledge — keying, ownership and the status lifecycle.

The merge rule has its own file (``test_knowledge_merge.py``); this one covers
everything around it: ``compose_key`` and its per-owner uniqueness, own → shared
resolution, and the transitions an agent drives through
``PUT /projects/{key}/repos/{repo}/knowledge``.
"""

from __future__ import annotations

import pytest
from sqlalchemy.exc import IntegrityError

from app.config import AUDIENCE_QAGENT
from app.models.knowledge import ProjectKnowledge, compose_key, split_key

PASSWORD = "password12345"


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


def _knowledge(db, project_key, repo, owner_id, **kwargs):
    row = ProjectKnowledge(
        key=compose_key(project_key, repo),
        project_key=project_key,
        repo=repo,
        name=project_key,
        owner_id=owner_id,
        **kwargs,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


# ---------------------------------------------------------------- compose_key
def test_compose_key_is_qagents_format():
    assert compose_key("Surency Platform", "web") == "Surency Platform::web"
    assert compose_key("Surency Platform") == "Surency Platform"
    assert compose_key("Surency Platform", "") == "Surency Platform"


def test_split_key_inverts_compose_key():
    assert split_key("Surency Platform::web") == ("Surency Platform", "web")
    assert split_key("Surency Platform") == ("Surency Platform", "")


def test_compose_key_is_unique_per_owner(db_session, alice, bob):
    _knowledge(db_session, "shop", "web", alice.id)
    _knowledge(db_session, "shop", "web", bob.id)  # other namespace — fine
    _knowledge(db_session, "shop", "web", None)  # shared — fine
    # …and a different repo under the same project is a different key.
    _knowledge(db_session, "shop", "api", alice.id)

    db_session.add(
        ProjectKnowledge(key=compose_key("shop", "web"), project_key="shop", owner_id=alice.id)
    )
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


# ---------------------------------------------------------------- reads
def test_reads_resolve_own_then_shared(client, db_session, alice, auth_headers):
    _knowledge(db_session, "shop", "web", None, confidence=10)
    _knowledge(db_session, "shop", "web", alice.id, confidence=90)

    body = client.get(
        "/projects/shop/repos/web/knowledge", headers=auth_headers("alice@emesoft.net", PASSWORD)
    ).json()
    assert body["confidence"] == 90
    assert body["shared"] is False


def test_a_member_falls_back_to_the_shared_knowledge(client, db_session, alice, auth_headers):
    _knowledge(db_session, "shop", "web", None, confidence=10)
    body = client.get(
        "/projects/shop/repos/web/knowledge", headers=auth_headers("alice@emesoft.net", PASSWORD)
    ).json()
    assert body["confidence"] == 10
    assert body["shared"] is True


def test_another_members_knowledge_is_invisible(client, db_session, alice, bob, auth_headers):
    _knowledge(db_session, "shop", "web", alice.id, confidence=90)
    response = client.get(
        "/projects/shop/repos/web/knowledge", headers=auth_headers("bob@emesoft.net", PASSWORD)
    )
    assert response.status_code == 404


def test_a_repo_read_falls_back_to_project_level_knowledge(
    client, db_session, alice, auth_headers
):
    """A project indexed before per-repo knowledge existed still grounds a run."""
    _knowledge(db_session, "shop", "", alice.id, confidence=42)
    body = client.get(
        "/projects/shop/repos/web/knowledge", headers=auth_headers("alice@emesoft.net", PASSWORD)
    ).json()
    assert body["confidence"] == 42
    assert body["repo"] == ""


def test_project_level_knowledge_does_not_pick_up_a_repo_row(
    client, db_session, alice, auth_headers
):
    _knowledge(db_session, "shop", "web", alice.id)
    response = client.get(
        "/projects/shop/knowledge", headers=auth_headers("alice@emesoft.net", PASSWORD)
    )
    assert response.status_code == 404


def test_an_agent_token_may_read_knowledge(client, db_session, alice, agent_headers):
    _knowledge(db_session, "shop", "web", alice.id)
    headers = agent_headers("alice@emesoft.net")
    assert client.get("/projects/shop/repos/web/knowledge", headers=headers).status_code == 200


def test_knowledge_requires_authentication(client):
    assert client.get("/projects/shop/repos/web/knowledge").status_code == 401
    assert client.patch("/projects/shop/repos/web/knowledge", json={}).status_code == 401


# ---------------------------------------------------------------- lifecycle
def _report(client, headers, **patch):
    response = client.put("/projects/shop/repos/web/knowledge", json=patch, headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


def test_the_full_status_lifecycle(client, alice, agent_headers):
    """not_indexed → indexing → indexed → error → indexed → stale, with the
    version, timestamp and error field behaving at each step."""
    headers = agent_headers("alice@emesoft.net")

    created = _report(client, headers, name="Shop", provider="github")
    assert created["status"] == "not_indexed"
    assert created["version"] == "v1"
    assert created["lastIndexed"] is None

    indexing = _report(client, headers, status="indexing")
    assert indexing["status"] == "indexing"
    assert indexing["lastIndexed"] is None
    assert indexing["version"] == "v1"

    indexed = _report(
        client,
        headers,
        status="indexed",
        confidence=88,
        knowledge={"domain": "retail", "routes": []},
        docPath="/home/agent/workspace/knowledge/shop/web",
    )
    # First successful index stays v1 (QAgent's rule).
    assert indexed["version"] == "v1"
    assert indexed["status"] == "indexed"
    assert indexed["confidence"] == 88
    assert indexed["lastIndexed"] is not None
    assert indexed["needsRefresh"] is False
    assert indexed["lastError"] == ""
    assert indexed["docPath"] == "/home/agent/workspace/knowledge/shop/web"

    failed = _report(client, headers, status="error", lastError="clone failed: auth")
    assert failed["status"] == "error"
    assert failed["lastError"] == "clone failed: auth"
    assert failed["version"] == "v1"

    rebuilt = _report(client, headers, status="indexed", confidence=91)
    # A rebuild increments, and clears the stale error message.
    assert rebuilt["version"] == "v2"
    assert rebuilt["lastError"] == ""

    stale = _report(client, headers, status="stale", needsRefresh=True)
    assert stale["status"] == "stale"
    assert stale["needsRefresh"] is True
    assert stale["version"] == "v2"


def test_confidence_is_clamped(client, alice, agent_headers):
    headers = agent_headers("alice@emesoft.net")
    assert _report(client, headers, confidence=400)["confidence"] == 100
    assert _report(client, headers, confidence=-5)["confidence"] == 0


def test_an_unknown_status_is_refused(client, alice, agent_headers):
    response = client.put(
        "/projects/shop/repos/web/knowledge",
        json={"status": "definitely_not_a_status"},
        headers=agent_headers("alice@emesoft.net"),
    )
    assert response.status_code == 400


def test_a_report_lands_in_the_callers_namespace(
    client, db_session, admin, alice, auth_headers, agent_headers
):
    """A member reporting against a key that only exists shared creates their own
    row rather than rewriting everyone's."""
    _knowledge(db_session, "shop", "web", None, confidence=10)
    _report(client, agent_headers("alice@emesoft.net"), status="indexed", confidence=90)

    rows = {
        r.owner_id: r.confidence
        for r in db_session.query(ProjectKnowledge)
        .filter(ProjectKnowledge.key == compose_key("shop", "web"))
        .all()
    }
    assert rows == {None: 10, alice.id: 90}


def test_an_admin_reports_onto_the_shared_row(client, db_session, admin, agent_headers):
    _knowledge(db_session, "shop", "web", None, confidence=10)
    body = _report(client, agent_headers("admin@emesoft.net"), status="indexed", confidence=95)
    assert body["shared"] is True
    assert (
        db_session.query(ProjectKnowledge)
        .filter(ProjectKnowledge.key == compose_key("shop", "web"))
        .count()
        == 1
    )
