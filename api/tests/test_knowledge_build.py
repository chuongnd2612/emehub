"""Hub-side knowledge builds (ADR 0007).

Five properties, in the order they matter:

1. **The endpoint is a handoff, not the work.** It commits ``indexing`` and
   returns; the build happens on a thread afterwards.
2. **Requesting twice does not build twice.**
3. **The concurrency cap holds** — one member cannot start N builds and have
   them all run.
4. **Failure is a status.** A clone that fails lands ``error`` with a message a
   human can act on, and the endpoint never 500s.
5. **The PAT never escapes.** It is injected into the clone URL, git reflects
   that URL back in its error output, and neither the log nor ``last_error``
   nor the response may contain it.

The build worker's *body* is stubbed in the concurrency tests
(``knowledge_service._build``) so the semaphore and the in-flight set are the
real code under test. The failure tests stub ``subprocess.run`` instead, so the
whole clone path — URL construction, the git failure, the scrubbing — runs for
real against a git that is not there.
"""

from __future__ import annotations

import logging
import threading
import time

import pytest

from app import crypto
from app.config import AUDIENCE_QAGENT
from app.models.knowledge import ProjectKnowledge, compose_key
from app.models.project import Project
from app.models.project_config import ProjectConfig
from app.models.provider_connection import ProviderConnection
from app.services import connection_service, knowledge_service, repo_service

PASSWORD = "password12345"
#: Long enough that ``adapters.base.scrub`` will act on it, and distinctive
#: enough that a substring search is meaningful.
PAT = "ghp_averyrealisticlookingtokenvalue0123456789"
REPO_URL = "https://github.com/emesoft/surency-web.git"


# ------------------------------------------------------------------ fixtures
@pytest.fixture(autouse=True)
def reset_build_state():
    """Builds are process-global state; no test may inherit another's.

    Both the in-flight set and the lazily-built semaphore are cleared, so a test
    that changed ``knowledge_build_concurrency`` cannot leave a stale cap behind.
    """
    yield
    with knowledge_service._BUILD_LOCK:
        knowledge_service._building.clear()
    knowledge_service._semaphore = None
    knowledge_service._semaphore_capacity = 0


@pytest.fixture
def alice(make_user):
    return make_user("alice@emesoft.net", PASSWORD)


@pytest.fixture
def project(db_session, alice):
    """A project with one repository, bound to a PAT-carrying connection."""
    db_session.add(Project(key="surency", name="Surency", owner_id=alice.id))
    connection = ProviderConnection(
        kind="github",
        label="GitHub",
        base_url="https://github.com",
        pat_encrypted=crypto.encrypt(PAT),
        capabilities=connection_service.default_capabilities("github"),
        owner_id=alice.id,
    )
    db_session.add(connection)
    db_session.commit()
    db_session.add(
        ProjectConfig(
            key="surency",
            name="Surency",
            repository_connection_id=connection.id,
            repos=[
                {
                    "name": "web",
                    "repo_url": REPO_URL,
                    "default_branch": "main",
                    "local_repo_path": "/home/agent/checkouts/web",
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


def _row(db, project_key="surency", repo="web"):
    return (
        db.query(ProjectKnowledge)
        .filter(ProjectKnowledge.key == compose_key(project_key, repo))
        .first()
    )


class _Gate:
    """A build body that blocks until released, and counts overlap."""

    def __init__(self) -> None:
        self.release = threading.Event()
        self.entered = threading.Semaphore(0)
        self.lock = threading.Lock()
        self.live = 0
        self.peak = 0
        self.calls: list[int] = []

    def __call__(self, db, row_id):  # matches _build's signature
        with self.lock:
            self.calls.append(row_id)
            self.live += 1
            self.peak = max(self.peak, self.live)
        self.entered.release()
        self.release.wait(timeout=10)
        with self.lock:
            self.live -= 1

    def wait_for(self, n: int, timeout: float = 5.0) -> bool:
        """Block until ``n`` builds have entered the body."""
        deadline = time.monotonic() + timeout
        for _ in range(n):
            if not self.entered.acquire(timeout=max(0.0, deadline - time.monotonic())):
                return False
        return True

    def finish(self) -> None:
        self.release.set()


@pytest.fixture
def gate(monkeypatch):
    blocker = _Gate()
    monkeypatch.setattr(knowledge_service, "_build", blocker)
    yield blocker
    blocker.finish()
    # Let the daemon threads unwind so they cannot touch the next test's DB.
    for _ in range(200):
        if not knowledge_service._building:
            break
        time.sleep(0.01)


# ------------------------------------------------------- the endpoint hands off
def test_the_endpoint_commits_indexing_before_it_returns(client, headers, project, gate):
    response = client.post(f"/projects/{project}/repos/web/knowledge/build", headers=headers)

    assert response.status_code == 202, response.text
    assert response.json()["status"] == "indexing"
    # …and it is committed, not merely pending: the worker thread reads the row
    # through its own session and must see `indexing` there.
    assert gate.wait_for(1)
    assert gate.calls  # the worker did start


def test_a_read_sees_indexing_immediately(client, headers, project, gate):
    client.post(f"/projects/{project}/repos/web/knowledge/build", headers=headers)
    assert gate.wait_for(1)

    read = client.get(f"/projects/{project}/repos/web/knowledge", headers=headers)
    assert read.status_code == 200
    assert read.json()["status"] == "indexing"


def test_a_second_request_does_not_double_start(client, headers, project, gate):
    first = client.post(f"/projects/{project}/repos/web/knowledge/build", headers=headers)
    assert gate.wait_for(1)

    second = client.post(f"/projects/{project}/repos/web/knowledge/build", headers=headers)

    # Same answer to the caller — from their point of view a build is running.
    assert second.status_code == 202
    assert second.json()["status"] == "indexing"
    assert second.json()["id"] == first.json()["id"]
    # …but only one worker ever entered the build body.
    time.sleep(0.2)
    assert len(gate.calls) == 1


def test_only_the_hub_audience_may_spend_money(client, login, alice, project):
    """A build clones a repo and burns Claude tokens — an agent token cannot."""
    agent = {"Authorization": f"Bearer {login(alice.email, PASSWORD)['tokens'][AUDIENCE_QAGENT]}"}

    response = client.post(f"/projects/{project}/repos/web/knowledge/build", headers=agent)

    assert response.status_code in (401, 403), response.text


def test_an_unknown_project_is_a_404_not_a_build(client, headers, project, gate):
    response = client.post("/projects/nope/repos/web/knowledge/build", headers=headers)

    assert response.status_code == 404
    assert not gate.calls


# ------------------------------------------------------------- concurrency cap
def test_the_concurrency_cap_holds(db_session, alice, monkeypatch, gate):
    """Three builds, a cap of one: the third must wait, not run."""
    from app.config import settings

    monkeypatch.setattr(settings, "knowledge_build_concurrency", 1)
    knowledge_service._semaphore = None
    knowledge_service._semaphore_capacity = 0

    rows = []
    for repo in ("web", "api", "worker"):
        row = ProjectKnowledge(
            key=compose_key("surency", repo),
            project_key="surency",
            repo=repo,
            name="Surency",
            owner_id=alice.id,
        )
        db_session.add(row)
        rows.append(row)
    db_session.commit()

    for row in rows:
        assert knowledge_service.start_build(row.id) is True

    assert gate.wait_for(1)
    # Give the other two every chance to slip past the cap.
    time.sleep(0.3)
    assert gate.peak == 1, f"the cap leaked: {gate.peak} builds ran at once"
    assert len(gate.calls) == 1

    # Queued, not dropped: releasing the first lets the rest through.
    gate.finish()
    assert gate.wait_for(2)
    assert len(gate.calls) == 3


def test_the_cap_is_a_setting_and_is_rebuilt_when_it_changes(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "knowledge_build_concurrency", 3)
    knowledge_service._semaphore = None
    assert knowledge_service._build_semaphore()._initial_value == 3

    monkeypatch.setattr(settings, "knowledge_build_concurrency", 5)
    assert knowledge_service._build_semaphore()._initial_value == 5


def test_a_cap_below_one_is_clamped_rather_than_disabling_builds(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "knowledge_build_concurrency", 0)
    knowledge_service._semaphore = None
    assert knowledge_service._build_semaphore()._initial_value == 1


# ------------------------------------------------- failure is a status, not 500
def _fail_git_echoing_the_url(monkeypatch, seen: list[list[str]]):
    """Make every git call fail the way a real one does — quoting the URL it was
    given, credentials and all."""
    import subprocess

    class _Failed:
        returncode = 128
        stdout = ""

        def __init__(self, url: str) -> None:
            self.stderr = (
                f"remote: Invalid username or password.\n"
                f"fatal: Authentication failed for '{url}'\n"
            )

    def fake_run(args, **_kwargs):
        seen.append(list(args))
        url = next((a for a in args if isinstance(a, str) and a.startswith("http")), "")
        return _Failed(url)

    monkeypatch.setattr(subprocess, "run", fake_run)


def test_a_failed_clone_lands_error_with_a_scrubbed_message(
    db_session, alice, project, monkeypatch, caplog
):
    caplog.set_level(logging.DEBUG)
    seen: list[list[str]] = []
    _fail_git_echoing_the_url(monkeypatch, seen)

    row = ProjectKnowledge(
        key=compose_key("surency", "web"),
        project_key="surency",
        repo="web",
        name="Surency",
        status="indexing",
        owner_id=alice.id,
    )
    db_session.add(row)
    db_session.commit()

    # Run the worker inline — this is the real _build, the real repo_service and
    # the real failure handler.
    knowledge_service._run_build(row.id)

    db_session.expire_all()
    row = _row(db_session)
    assert row.status == "error"
    assert row.last_error, "a failed build must say why"

    # The PAT really was in play — otherwise this test proves nothing.
    assert any(any(PAT in str(a) for a in call) for call in seen), (
        "the clone did not authenticate; the scrubbing assertions below are vacuous"
    )
    # …and it is in none of the places a human or a log aggregator can read.
    assert PAT not in row.last_error
    assert PAT not in caplog.text
    assert "***@" in row.last_error or "github.com" in row.last_error
    assert "Authentication failed" in row.last_error


def test_the_pat_never_reaches_a_log_line(db_session, alice, project, monkeypatch, caplog):
    caplog.set_level(logging.DEBUG)
    seen: list[list[str]] = []
    _fail_git_echoing_the_url(monkeypatch, seen)

    row = ProjectKnowledge(
        key=compose_key("surency", "web"),
        project_key="surency",
        repo="web",
        name="Surency",
        status="indexing",
        owner_id=alice.id,
    )
    db_session.add(row)
    db_session.commit()
    knowledge_service._run_build(row.id)

    assert caplog.text, "the build logged nothing at all — the assertion is vacuous"
    assert PAT not in caplog.text
    assert "***@github.com" in caplog.text


def test_a_missing_repository_connection_is_an_error_status(db_session, alice, monkeypatch):
    """No connection at all — the row must say so, not raise."""
    db_session.add(Project(key="orphan", name="Orphan", owner_id=alice.id))
    db_session.add(
        ProjectConfig(
            key="orphan",
            name="Orphan",
            repos=[{"name": "web", "repo_url": REPO_URL, "default": True}],
            owner_id=alice.id,
        )
    )
    row = ProjectKnowledge(
        key=compose_key("orphan", "web"),
        project_key="orphan",
        repo="web",
        name="Orphan",
        status="indexing",
        owner_id=alice.id,
    )
    db_session.add(row)
    db_session.commit()

    knowledge_service._run_build(row.id)

    db_session.expire_all()
    row = _row(db_session, "orphan")
    assert row.status == "error"
    assert "repository connection" in row.last_error.lower()


def test_a_repo_with_no_clone_url_is_an_actionable_error(db_session, alice, project):
    row = ProjectKnowledge(
        key=compose_key("surency", "mobile"),
        project_key="surency",
        repo="mobile",
        name="Surency",
        status="indexing",
        owner_id=alice.id,
    )
    db_session.add(row)
    db_session.commit()

    knowledge_service._run_build(row.id)

    db_session.expire_all()
    row = _row(db_session, repo="mobile")
    assert row.status == "error"
    assert "Repositories" in row.last_error


def test_a_missing_claude_credential_is_an_error_status(
    db_session, alice, project, monkeypatch, tmp_path
):
    """The clone succeeds, the CLI never runs: nobody has uploaded a credential."""
    clone = tmp_path / "clone"
    clone.mkdir()
    monkeypatch.setattr(repo_service, "ensure_clone", lambda *a, **k: clone)

    row = ProjectKnowledge(
        key=compose_key("surency", "web"),
        project_key="surency",
        repo="web",
        name="Surency",
        status="indexing",
        owner_id=alice.id,
    )
    db_session.add(row)
    db_session.commit()

    knowledge_service._run_build(row.id)

    db_session.expire_all()
    row = _row(db_session)
    assert row.status == "error"
    assert "Claude credential" in row.last_error


def test_the_worker_survives_a_row_that_vanished(db_session):
    """Deleting a project mid-build must not kill the worker thread."""
    knowledge_service._run_build(999_999)  # no row, no exception
