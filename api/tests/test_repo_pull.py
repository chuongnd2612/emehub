"""``POST /projects/{key}/repos/{repo}/pull`` — a sync, not a build (issue #279).

Distinct from ``knowledge/build`` (``test_knowledge_build.py``): no Claude CLI,
no background worker, no ``status``/``version`` movement. Four properties:

1. it creates a ``ProjectKnowledge`` row when none exists yet;
2. it stamps ``last_synced_at``/``synced_commit_sha`` on an existing row without
   touching its build lifecycle fields;
3. it resolves the repo's ``default_branch`` and passes it to
   ``repo_service.ensure_clone``;
4. it requires hub auth, same as the build endpoint.

``repo_service.ensure_clone`` and ``repo_service.head_commit`` are stubbed here
— the clone/branch mechanics themselves are covered end-to-end against real git
in ``test_repo_service.py``.
"""

from __future__ import annotations

import pytest

from app.config import AUDIENCE_QAGENT
from app.models.knowledge import STATUS_INDEXED, ProjectKnowledge, compose_key
from app.models.project import Project
from app.models.project_config import ProjectConfig
from app.services import knowledge_service, repo_service

PASSWORD = "password12345"
REPO_URL = "https://github.com/emesoft/surency-web.git"


@pytest.fixture
def alice(make_user):
    return make_user("alice@emesoft.net", PASSWORD)


@pytest.fixture
def project(db_session, alice):
    """A project with one repository configured for the ``release`` branch."""
    db_session.add(Project(key="surency", name="Surency", owner_id=alice.id))
    db_session.add(
        ProjectConfig(
            key="surency",
            name="Surency",
            repos=[
                {
                    "name": "web",
                    "repo_url": REPO_URL,
                    "default_branch": "release",
                    "local_repo_path": "",
                    "default": True,
                }
            ],
            owner_id=alice.id,
        )
    )
    db_session.commit()
    return "surency"


@pytest.fixture
def headers(auth_headers, alice):
    return auth_headers(alice.email, PASSWORD)


@pytest.fixture
def stub_clone(monkeypatch, tmp_path):
    """Stand in for the real clone/branch-resolve/rev-parse chain.

    Returns the ``(dest, sha)`` the stub answers with, and records the
    ``branch`` it was called with so the resolution path can be asserted.
    """
    dest = tmp_path / "clone"
    dest.mkdir()
    sha = "abc123def456"
    calls: dict = {}

    def fake_ensure_clone(*_args, **kwargs):
        calls["branch"] = kwargs.get("branch")
        return dest

    monkeypatch.setattr(repo_service, "ensure_clone", fake_ensure_clone)
    monkeypatch.setattr(repo_service, "head_commit", lambda _dest: sha)
    return calls, sha


def _row(db, project_key="surency", repo="web"):
    return (
        db.query(ProjectKnowledge)
        .filter(ProjectKnowledge.key == compose_key(project_key, repo))
        .first()
    )


# ------------------------------------------------------------ creates a row
def test_pull_creates_a_knowledge_row_when_absent(
    client, headers, project, db_session, stub_clone
):
    assert _row(db_session) is None

    response = client.post(f"/projects/{project}/repos/web/pull", headers=headers)

    assert response.status_code == 200, response.text
    row = _row(db_session)
    assert row is not None
    assert row.status == "not_indexed"  # a sync never builds


def test_pull_resolves_the_configured_branch(client, headers, project, stub_clone):
    calls, _sha = stub_clone

    response = client.post(f"/projects/{project}/repos/web/pull", headers=headers)

    assert response.status_code == 200, response.text
    assert calls["branch"] == "release"
    assert response.json()["branch"] == "release"


# ------------------------------------------------------- stamps timestamp/sha
def test_pull_updates_timestamp_and_sha_on_an_existing_row(
    client, headers, project, db_session, stub_clone, alice
):
    _calls, sha = stub_clone
    existing = ProjectKnowledge(
        key=compose_key("surency", "web"),
        project_key="surency",
        repo="web",
        name="Surency",
        status=STATUS_INDEXED,
        confidence=77,
        version="v3",
        owner_id=alice.id,  # alice's own row, so write_target resolves it directly
    )
    db_session.add(existing)
    db_session.commit()

    response = client.post(f"/projects/{project}/repos/web/pull", headers=headers)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["commitSha"] == sha
    assert body["syncedAt"] is not None

    db_session.expire_all()
    row = _row(db_session)
    # A sync must not touch the build lifecycle.
    assert row.status == STATUS_INDEXED
    assert row.confidence == 77
    assert row.version == "v3"
    assert row.synced_commit_sha == sha
    assert row.last_synced_at is not None


def test_pull_does_not_advance_build_fields_on_a_fresh_row(
    client, headers, project, db_session, stub_clone
):
    client.post(f"/projects/{project}/repos/web/pull", headers=headers)

    row = _row(db_session)
    assert row.status == "not_indexed"
    assert row.version == "v1"
    assert row.last_indexed is None


# --------------------------------------------------------------------- auth
def test_pull_requires_hub_auth(client, project, stub_clone):
    response = client.post(f"/projects/{project}/repos/web/pull")

    assert response.status_code == 401


def test_an_agent_token_may_not_pull(client, login, alice, project, stub_clone):
    """Mirrors the build endpoint: pulling clones a repo and touches the PAT."""
    agent = {"Authorization": f"Bearer {login(alice.email, PASSWORD)['tokens'][AUDIENCE_QAGENT]}"}

    response = client.post(f"/projects/{project}/repos/web/pull", headers=agent)

    assert response.status_code in (401, 403), response.text


def test_an_unknown_project_is_a_404_not_a_pull(client, headers, project, stub_clone):
    response = client.post("/projects/nope/repos/web/pull", headers=headers)

    assert response.status_code == 404


# ------------------------------------------------------------ error mapping
def test_a_clone_failure_is_a_502_not_a_500(client, headers, project, monkeypatch):
    def boom(*_args, **_kwargs):
        raise repo_service.CloneError("Could not clone https://github.com/x: fatal error")

    monkeypatch.setattr(repo_service, "ensure_clone", boom)

    response = client.post(f"/projects/{project}/repos/web/pull", headers=headers)

    assert response.status_code == 502
    assert "fatal error" in response.text


def test_an_unconfigured_repo_is_a_400(client, headers, project, stub_clone):
    response = client.post(f"/projects/{project}/repos/mobile/pull", headers=headers)

    assert response.status_code == 400
