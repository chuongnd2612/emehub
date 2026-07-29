"""Real knowledge-build progress (issue #68).

Q-Agent's build overlay ticks a ten-step checklist on a 620 ms timer, closes on
the POST response and toasts "built" before anything has been built. The point
of this file is that none of that can be true here, so each test is written as
the property that would catch the corresponding lie:

1. **The stages are recorded, and in the order the work happens.** Not ticked,
   not inferred — persisted, by the code that is about to do the thing.
2. **The Claude stage has real sub-progress.** The CLI is invoked with
   ``stream-json`` and the live message follows the tools it actually uses.
3. **…and it is scrubbed.** The message comes from a model reading a clone whose
   ``.git/config`` still holds an authenticated remote. It must not be able to
   carry a PAT into a database column or an API response.
4. **The writes are throttled.** A per-event UPDATE would be thousands per build.
5. **An orphaned row is detected.** A container that dies mid-build leaves
   ``indexing`` behind with no worker; the UI must be told, not left spinning.
6. **The POST says started, not built.** Nothing in the enqueue response may be
   mistaken for a finished build.
"""

from __future__ import annotations

import json
import subprocess
import time
from datetime import timedelta

import pytest

from app import crypto
from app.config import settings
from app.db import utcnow
from app.models.claude_credentials import ClaudeCredentials
from app.models.knowledge import (
    BUILD_STAGES,
    BUILD_TOTAL_STEPS,
    ProjectKnowledge,
    build_step,
    compose_key,
)
from app.models.project import Project
from app.models.project_config import ProjectConfig
from app.services import claude_cli, knowledge_service, repo_service
from tests.conftest import FakeClaudeProcess, stream_events

PASSWORD = "password12345"
PAT = "ghp_averyrealisticlookingtokenvalue0123456789"

CREDENTIAL = json.dumps(
    {
        "claudeAiOauth": {
            "accessToken": "sk-ant-oat-do-not-log-me",
            "refreshToken": "sk-ant-ort-also-secret",
            "expiresAt": 4_102_444_800_000,
            "scopes": ["user:inference"],
        }
    }
)

RESULT = json.dumps({"branch": "main", "stack": ["React"], "confidence": 88})


# ------------------------------------------------------------------ fixtures
@pytest.fixture(autouse=True)
def reset_build_state():
    yield
    with knowledge_service._BUILD_LOCK:
        knowledge_service._building.clear()
    knowledge_service._semaphore = None
    knowledge_service._semaphore_capacity = 0


@pytest.fixture
def alice(make_user):
    return make_user("alice@emesoft.net", PASSWORD)


@pytest.fixture
def headers(auth_headers, alice):
    return auth_headers(alice.email, PASSWORD)


@pytest.fixture
def project(db_session, alice):
    db_session.add(Project(key="surency", name="Surency", owner_id=alice.id))
    db_session.add(ClaudeCredentials(owner_id=alice.id, credentials=crypto.encrypt(CREDENTIAL)))
    db_session.add(
        ProjectConfig(
            key="surency",
            name="Surency",
            repos=[
                {"name": "web", "repo_url": "https://github.com/e/w.git", "default": True}
            ],
            owner_id=alice.id,
        )
    )
    db_session.commit()
    return "surency"


@pytest.fixture
def row(db_session, alice, project):
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
    return row


@pytest.fixture
def recorded(monkeypatch):
    """Every progress row actually committed, in order: ``(stage, message)``.

    Wrapping ``_persist`` rather than the public methods is deliberate — this
    records what reached the database, so a change that stopped persisting would
    fail the test instead of passing on the intent.
    """
    history: list[tuple[str, str]] = []
    original = knowledge_service.BuildProgress._persist

    def spy(self, stage, message, *, touch_only=False):
        original(self, stage, message, touch_only=touch_only)
        if not touch_only:
            history.append((stage, message))

    monkeypatch.setattr(knowledge_service.BuildProgress, "_persist", spy)
    return history


def _clone(monkeypatch, tmp_path):
    clone = tmp_path / "clone"
    clone.mkdir(exist_ok=True)
    monkeypatch.setattr(repo_service, "ensure_clone", lambda *a, **k: clone)
    return clone


def _stub_stream(monkeypatch, lines):
    seen: dict = {}

    def fake_popen(cmd, **kwargs):
        seen["cmd"] = list(cmd)
        seen["kwargs"] = kwargs
        return FakeClaudeProcess(lines)

    monkeypatch.setattr(subprocess, "Popen", fake_popen)
    return seen


# ------------------------------------------------- 1. the stages are recorded
def test_the_build_records_every_stage_in_the_order_it_happens(
    db_session, row, monkeypatch, tmp_path, recorded
):
    _clone(monkeypatch, tmp_path)
    _stub_stream(monkeypatch, stream_events(RESULT))

    knowledge_service._run_build(row.id)

    # Collapse the repeats: a live message re-writes the row under the stage it
    # belongs to, so `analyzing` legitimately appears more than once.
    ordered: list[str] = []
    for stage, _message in recorded:
        if not ordered or ordered[-1] != stage:
            ordered.append(stage)

    # `queued` is stamped by `begin_progress` on its own transient session
    # before the worker reaches the semaphore, so the in-build recorder — which
    # only sees `BuildProgress` — starts at `resolving`.
    assert ordered == ["resolving", "cloning", "analyzing", "writing"], recorded
    assert ["queued", *ordered] == list(BUILD_STAGES)


def test_a_queued_build_is_recorded_as_queued_not_as_nothing(db_session, row):
    """Over the concurrency cap a build waits with the row already `indexing`.

    That is a real state and the only honest thing to show, so `begin_progress`
    stamps it before the worker ever reaches the semaphore.
    """
    knowledge_service.begin_progress(db_session, row.id)

    db_session.expire_all()
    fresh = db_session.get(ProjectKnowledge, row.id)
    assert fresh.build_stage == "queued"
    assert fresh.build_step == 1
    assert fresh.build_message == "Waiting for a build slot"
    assert fresh.build_started_at is not None
    assert fresh.build_heartbeat_at is not None


def test_the_step_index_matches_the_stage_and_the_total_is_the_stage_count():
    assert [build_step(s) for s in BUILD_STAGES] == [1, 2, 3, 4, 5]
    assert BUILD_TOTAL_STEPS == len(BUILD_STAGES)
    assert build_step("") == 0
    assert build_step("not-a-stage") == 0


def test_a_settled_build_clears_the_stepper(db_session, row, monkeypatch, tmp_path):
    """`indexed` with a stage still set would keep the UI showing work in flight."""
    _clone(monkeypatch, tmp_path)
    _stub_stream(monkeypatch, stream_events(RESULT))

    knowledge_service._run_build(row.id)

    db_session.expire_all()
    fresh = db_session.get(ProjectKnowledge, row.id)
    assert fresh.status == "indexed"
    assert fresh.build_stage == ""
    assert fresh.build_step == 0
    assert fresh.build_message == ""
    assert fresh.build_heartbeat_at is None
    # …but when it started is worth keeping next to when it finished.
    assert fresh.build_started_at is not None


def test_a_failed_build_clears_the_stepper_too(db_session, row, monkeypatch, tmp_path):
    _clone(monkeypatch, tmp_path)
    monkeypatch.setattr(
        subprocess, "Popen", lambda *a, **k: FakeClaudeProcess([], returncode=1, stderr="boom")
    )

    knowledge_service._run_build(row.id)

    db_session.expire_all()
    fresh = db_session.get(ProjectKnowledge, row.id)
    assert fresh.status == "error"
    assert fresh.last_error
    assert fresh.build_stage == ""
    assert fresh.build_step == 0


# ------------------------------------------ 2. real sub-progress from Claude
def test_the_build_asks_the_cli_to_stream(db_session, row, monkeypatch, tmp_path):
    _clone(monkeypatch, tmp_path)
    seen = _stub_stream(monkeypatch, stream_events(RESULT))

    knowledge_service._run_build(row.id)

    cmd = seen["cmd"]
    assert "--output-format" in cmd
    assert cmd[cmd.index("--output-format") + 1] == "stream-json"
    assert "--verbose" in cmd


def test_the_live_message_follows_what_claude_is_actually_doing(
    db_session, row, monkeypatch, tmp_path, recorded
):
    _clone(monkeypatch, tmp_path)
    _stub_stream(
        monkeypatch,
        stream_events(RESULT, tools=("Read", "Grep"), targets=["/repo/api/app/main.py", "x"]),
    )
    # No throttle for this test: the point is the content, not the coalescing.
    monkeypatch.setattr(settings, "knowledge_progress_interval_s", 0.0)

    knowledge_service._run_build(row.id)

    analyzing = [message for stage, message in recorded if stage == "analyzing"]
    assert any("main.py" in m for m in analyzing), analyzing
    assert any(m.startswith("Reading") for m in analyzing), analyzing


def test_a_stream_handler_that_throws_does_not_lose_the_build(
    db_session, row, monkeypatch, tmp_path
):
    _clone(monkeypatch, tmp_path)
    _stub_stream(monkeypatch, stream_events(RESULT))
    monkeypatch.setattr(
        knowledge_service.BuildProgress,
        "on_claude_event",
        lambda self, event: (_ for _ in ()).throw(RuntimeError("nope")),
    )

    knowledge_service._run_build(row.id)

    db_session.expire_all()
    assert db_session.get(ProjectKnowledge, row.id).status == "indexed"


def test_describe_event_says_nothing_for_events_that_say_nothing():
    assert claude_cli.describe_event({"type": "user", "message": {"content": []}}) is None
    assert claude_cli.describe_event({"type": "result"}) is None
    assert claude_cli.describe_event("not an event") is None  # type: ignore[arg-type]
    assert claude_cli.describe_event({"type": "system", "subtype": "init"})


def test_the_blocking_path_is_untouched(db_session, monkeypatch, alice):
    """`run_json` without `on_event` must invoke and parse exactly as before."""
    db_session.add(ClaudeCredentials(owner_id=None, credentials=crypto.encrypt(CREDENTIAL)))
    db_session.commit()

    class _Completed:
        stdout = json.dumps({"type": "result", "result": RESULT})
        stderr = ""
        returncode = 0

    seen: dict = {}

    def fake_run(cmd, **kwargs):
        seen["cmd"] = list(cmd)
        return _Completed()

    monkeypatch.setattr(subprocess, "run", fake_run)
    monkeypatch.setattr(
        subprocess, "Popen", lambda *a, **k: pytest.fail("the blocking path must not Popen")
    )

    parsed = claude_cli.run_json("go", db=db_session, owner_id=None)

    assert parsed["confidence"] == 88
    assert seen["cmd"][seen["cmd"].index("--output-format") + 1] == "json"
    assert "--verbose" not in seen["cmd"]


def test_streaming_still_records_usage_and_cost(db_session, monkeypatch):
    """`run_json`'s contract is unchanged by streaming: the terminal `result`
    event is the same envelope the blocking format prints whole."""
    from app.models.claude_usage import ClaudeUsage

    db_session.add(ClaudeCredentials(owner_id=None, credentials=crypto.encrypt(CREDENTIAL)))
    db_session.commit()
    monkeypatch.setattr(
        subprocess, "Popen", lambda *a, **k: FakeClaudeProcess(stream_events(RESULT))
    )

    parsed = claude_cli.run_json("go", db=db_session, owner_id=None, on_event=lambda e: None)

    assert parsed["confidence"] == 88
    usage = db_session.query(ClaudeUsage).all()
    assert usage, "a streamed call must still be attributed"
    assert usage[-1].input_tokens == 1200
    assert float(usage[-1].cost_usd) == pytest.approx(0.0412)


def test_a_stream_that_never_returns_a_result_is_an_error_not_a_knowledge_base(
    db_session, monkeypatch
):
    """Without this the init event would parse as JSON and become the payload."""
    db_session.add(ClaudeCredentials(owner_id=None, credentials=crypto.encrypt(CREDENTIAL)))
    db_session.commit()
    lines = [json.dumps({"type": "system", "subtype": "init", "session_id": "s1"})]
    monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: FakeClaudeProcess(lines))

    with pytest.raises(claude_cli.ClaudeError):
        claude_cli.run_json("go", db=db_session, owner_id=None, on_event=lambda e: None)


# ------------------------------------------------------- 3. the message is safe
def test_a_credential_in_the_stream_never_reaches_the_column(
    db_session, row, monkeypatch, tmp_path, recorded
):
    """Claude runs inside a clone whose `.git/config` holds the authed remote."""
    leaky = f"https://x-access-token:{PAT}@github.com/e/w.git"
    _clone(monkeypatch, tmp_path)
    _stub_stream(monkeypatch, stream_events(RESULT, tools=("Read",), targets=[leaky]))
    monkeypatch.setattr(settings, "knowledge_progress_interval_s", 0.0)

    knowledge_service._run_build(row.id)

    assert recorded, "nothing was recorded — the assertion below would be vacuous"
    for _stage, message in recorded:
        assert PAT not in message
    assert any("***" in message for _stage, message in recorded)


def test_a_bare_token_is_scrubbed_even_with_no_url_around_it():
    cleaned = knowledge_service.scrub_progress_message(f"Reading {PAT}")
    assert PAT not in cleaned
    assert "***" in cleaned


def test_the_message_is_collapsed_and_bounded():
    from app.models.knowledge import BUILD_MESSAGE_LIMIT

    cleaned = knowledge_service.scrub_progress_message("a\nb\t  c")
    assert cleaned == "a b c"
    assert len(knowledge_service.scrub_progress_message("x" * 5000)) <= BUILD_MESSAGE_LIMIT


# ------------------------------------------------------- 4. writes are throttled
def test_a_flood_of_events_produces_one_write(db_session, row):
    progress = knowledge_service.BuildProgress(db_session, row.id, interval=30.0)
    progress.stage("analyzing")
    writes_after_stage = progress.writes

    for i in range(500):
        progress.message(f"Reading file_{i}.py")

    assert progress.writes == writes_after_stage, (
        f"{progress.writes - writes_after_stage} message writes slipped past the throttle"
    )


def test_the_throttle_reopens_once_the_interval_elapses(db_session, row):
    progress = knowledge_service.BuildProgress(db_session, row.id, interval=0.05)
    progress.stage("analyzing")
    before = progress.writes

    progress.message("Reading a.py")  # inside the window — dropped
    time.sleep(0.06)
    progress.message("Reading b.py")  # window reopened — written

    assert progress.writes == before + 1
    db_session.expire_all()
    assert db_session.get(ProjectKnowledge, row.id).build_message == "Reading b.py"


def test_an_unchanged_message_is_never_rewritten(db_session, row):
    progress = knowledge_service.BuildProgress(db_session, row.id, interval=0.0)
    progress.stage("analyzing")
    progress.message("Reading a.py")
    before = progress.writes

    for _ in range(20):
        progress.message("Reading a.py")

    assert progress.writes == before


def test_a_stage_change_is_never_throttled(db_session, row):
    """Five stages in a build that lasts minutes: they are the signal."""
    progress = knowledge_service.BuildProgress(db_session, row.id, interval=3600.0)

    for stage in BUILD_STAGES:
        progress.stage(stage)

    assert progress.writes == len(BUILD_STAGES)
    db_session.expire_all()
    assert db_session.get(ProjectKnowledge, row.id).build_stage == BUILD_STAGES[-1]


# ------------------------------------------------------------- 5. orphan detection
def test_a_row_left_indexing_by_a_dead_container_is_detected(db_session, row):
    row.build_stage = "analyzing"
    row.build_step = 4
    row.build_started_at = utcnow() - timedelta(hours=1)
    row.build_heartbeat_at = utcnow() - timedelta(hours=1)
    db_session.commit()

    assert not knowledge_service.is_building(row.id), "no worker exists in this process"
    assert knowledge_service.is_orphaned(row) is True


def test_a_live_build_is_not_called_orphaned(db_session, row):
    row.build_stage = "analyzing"
    row.build_heartbeat_at = utcnow()
    db_session.commit()

    assert knowledge_service.is_orphaned(row) is False


def test_a_build_running_in_this_process_is_never_orphaned(db_session, row):
    """`is_building` is authoritative positively — a slow build with a stale
    heartbeat is still a build."""
    row.build_started_at = utcnow() - timedelta(hours=1)
    row.build_heartbeat_at = utcnow() - timedelta(hours=1)
    db_session.commit()
    with knowledge_service._BUILD_LOCK:
        knowledge_service._building.add(row.id)

    assert knowledge_service.is_orphaned(row) is False


def test_a_settled_row_is_never_orphaned(db_session, row):
    row.status = "indexed"
    row.build_heartbeat_at = utcnow() - timedelta(days=1)
    db_session.commit()

    assert knowledge_service.is_orphaned(row) is False


def test_an_agent_reported_indexing_row_is_left_alone(db_session, row):
    """`PUT …/knowledge` can set `indexing` from an agent host. The hub is not
    that build's worker and has no standing to call it abandoned."""
    row.build_started_at = None
    row.build_heartbeat_at = None
    db_session.commit()

    assert knowledge_service.is_orphaned(row) is False


def test_the_read_endpoint_surfaces_the_orphan(client, headers, project, db_session, row):
    row.build_stage = "cloning"
    row.build_step = 3
    row.build_message = "Cloning web"
    row.build_started_at = utcnow() - timedelta(hours=2)
    row.build_heartbeat_at = utcnow() - timedelta(hours=2)
    db_session.commit()

    body = client.get(f"/projects/{project}/repos/web/knowledge", headers=headers).json()

    assert body["status"] == "indexing"
    assert body["buildOrphaned"] is True
    assert body["buildStage"] == "cloning"
    assert body["buildStep"] == 3
    assert body["buildTotalSteps"] == BUILD_TOTAL_STEPS
    assert body["buildMessage"] == "Cloning web"
    assert body["buildStartedAt"]


# --------------------------------------------- 6. the POST says started, not built
def test_the_post_response_says_started_not_built(client, headers, project, monkeypatch):
    """Q-Agent toasts "Project Knowledge built" off this response. Nothing in it
    may support that reading."""
    monkeypatch.setattr(knowledge_service, "_build", lambda db, row_id: None)

    response = client.post(
        f"/projects/{project}/repos/web/knowledge/build", headers=headers
    )

    assert response.status_code == 202
    body = response.json()
    assert body["status"] == "indexing"
    assert body["buildStage"] == "queued"
    assert body["buildStep"] == 1
    assert body["buildMessage"] == "Waiting for a build slot"
    assert body["buildStartedAt"], "the elapsed clock starts at enqueue"
    # The three things that would let a client claim completion.
    assert body["lastIndexed"] is None
    assert body["confidence"] == 0
    assert body["knowledge"] == {}


def test_the_read_carries_progress_while_the_build_runs(
    client, headers, project, db_session, row
):
    row.build_stage = "analyzing"
    row.build_step = 4
    row.build_message = "Reading …/app/main.py"
    row.build_started_at = utcnow()
    row.build_heartbeat_at = utcnow()
    db_session.commit()

    body = client.get(f"/projects/{project}/repos/web/knowledge", headers=headers).json()

    assert body["buildStage"] == "analyzing"
    assert body["buildStep"] == 4
    assert body["buildMessage"] == "Reading …/app/main.py"
    assert body["buildOrphaned"] is False
