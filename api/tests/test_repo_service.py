"""``repo_service.ensure_clone`` branch targeting (issue #279).

These run against a real local git repository (no network — a ``file://``-style
local path is exactly as far as a private-repo clone can be pushed without a
PAT-bearing remote) so the assertions are about git's actual behaviour, not
about the argv this module happens to build. Three properties, matching the
issue's scope:

1. a fresh clone with a branch checks that branch out, single-branch and
   shallow;
2. an existing checkout already on the requested branch is refreshed in place
   (fetch + reset), not re-cloned;
3. an existing checkout on a *different* branch is wiped and re-cloned, because
   a shallow single-branch clone cannot switch branches.
"""

from __future__ import annotations

import subprocess

import pytest

from app.models.project import Project
from app.models.provider_connection import ProviderConnection
from app.services import connection_service, repo_service
from app.services.workspace_scope import scoped_repos_dir


def _git(*args: str, cwd) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True)


@pytest.fixture
def origin(tmp_path):
    """A local repository with two branches, each with its own commit."""
    repo = tmp_path / "origin.git"
    repo.mkdir()
    _git("init", "-b", "main", cwd=repo)
    _git("config", "user.email", "test@example.com", cwd=repo)
    _git("config", "user.name", "Test", cwd=repo)
    (repo / "README.md").write_text("main\n", encoding="utf-8")
    _git("add", "README.md", cwd=repo)
    _git("commit", "-m", "on main", cwd=repo)

    _git("checkout", "-b", "feature", cwd=repo)
    (repo / "README.md").write_text("feature\n", encoding="utf-8")
    _git("commit", "-am", "on feature", cwd=repo)

    _git("checkout", "main", cwd=repo)
    return repo


@pytest.fixture
def alice(make_user):
    return make_user("alice@emesoft.net", "password12345")


@pytest.fixture
def connection(db_session, alice):
    """A repository-capable connection with no PAT — the origin is local."""
    conn = ProviderConnection(
        kind="github",
        label="GitHub",
        base_url="https://github.com",
        pat_encrypted="",
        capabilities=connection_service.default_capabilities("github"),
        owner_id=alice.id,
    )
    db_session.add(conn)
    db_session.add(Project(key="surency", name="Surency", owner_id=alice.id))
    db_session.commit()
    return conn


def _clone(db_session, origin, alice, connection, *, branch=None):
    return repo_service.ensure_clone(
        db_session,
        project_key="surency",
        repo_name="web",
        repo_url=str(origin),
        owner_id=alice.id,
        bound_connection_id=connection.id,
        branch=branch,
    )


def _current_branch(dest) -> str:
    proc = subprocess.run(
        ["git", "-C", str(dest), "rev-parse", "--abbrev-ref", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    )
    return proc.stdout.strip()


# ------------------------------------------------------------ fresh clone
def test_fresh_clone_with_branch_checks_out_that_branch(db_session, origin, alice, connection):
    dest = _clone(db_session, origin, alice, connection, branch="feature")

    assert _current_branch(dest) == "feature"
    assert (dest / "README.md").read_text(encoding="utf-8") == "feature\n"
    # single-branch: only the requested branch's remote ref exists
    proc = subprocess.run(
        ["git", "-C", str(dest), "branch", "-r"], check=True, capture_output=True, text=True
    )
    assert "origin/feature" in proc.stdout
    assert "origin/main" not in proc.stdout


def test_fresh_clone_with_no_branch_follows_default_head(db_session, origin, alice, connection):
    dest = _clone(db_session, origin, alice, connection, branch=None)

    assert _current_branch(dest) == "main"


# --------------------------------------------------------- refresh in place
def test_refresh_on_the_same_branch_fetches_and_resets(db_session, origin, alice, connection):
    dest = _clone(db_session, origin, alice, connection, branch="main")
    marker = dest / ".git" / "this_is_the_original_clone"
    marker.write_text("x", encoding="utf-8")

    # Advance the remote's main branch.
    (origin / "README.md").write_text("main v2\n", encoding="utf-8")
    _git("commit", "-am", "advance main", cwd=origin)

    dest2 = _clone(db_session, origin, alice, connection, branch="main")

    assert dest2 == dest
    assert marker.exists(), "same-branch refresh must not wipe and re-clone"
    assert (dest / "README.md").read_text(encoding="utf-8") == "main v2\n"
    assert _current_branch(dest) == "main"


# --------------------------------------------------------- reclone on switch
def test_a_different_branch_forces_a_reclone(db_session, origin, alice, connection):
    dest = _clone(db_session, origin, alice, connection, branch="main")
    marker = dest / ".git" / "this_is_the_original_clone"
    marker.write_text("x", encoding="utf-8")

    dest2 = _clone(db_session, origin, alice, connection, branch="feature")

    assert dest2 == dest
    assert not marker.exists(), "a branch switch must wipe the old shallow clone"
    assert _current_branch(dest) == "feature"
    assert (dest / "README.md").read_text(encoding="utf-8") == "feature\n"


def test_the_scoped_destination_is_under_the_owners_workspace(db_session, origin, alice, connection):
    dest = _clone(db_session, origin, alice, connection, branch="main")

    assert dest.is_relative_to(scoped_repos_dir(alice.id))
