"""Claude Code CLI integration — the one-shot JSON path, and a streaming twin.

ADR 0007 lets the hub build the shared artefacts it already owns the inputs for.
That is one job (``project-bootstrap``) and one invocation shape::

    claude -p "<prompt>" --output-format json --model <model> --effort <level>
           --append-system-prompt "<SKILL.md>"

run in the repository clone's directory, under a ``CLAUDE_CONFIG_DIR`` holding
the materialised credential.

``--model`` and ``--effort`` are resolved per *owner*, not per deployment (#190):
:func:`_resolve_model` asks :mod:`app.services.model_preferences` what the owner
of the work chose in Claude Settings, falling back to ``settings.claude_model``
and the default effort when they have chosen nothing — or when the work has no
owner at all.

## The streaming variant (issue #68)

A knowledge build spends most of its multi-minute wall time inside that one
subprocess, and ``--output-format json`` emits nothing until it is over — so
there is no per-tool signal available even in principle. Passing ``on_event``
switches the invocation to::

    claude -p "<prompt>" --output-format stream-json --verbose …

and reads stdout **line by line**, handing each decoded NDJSON event to the
callback as it arrives. The caller turns those into a live status line.

It is deliberately an *opt-in argument*, not a second function and not a change
of default: with ``on_event=None`` — every existing call site — the command,
the subprocess call and the parsing are exactly what they were. What the two
paths share is everything that matters afterwards, because ``stream-json``'s
terminal ``{"type": "result", …}`` event carries the same envelope
``--output-format json`` prints whole: ``result``, ``usage``, ``modelUsage``,
``total_cost_usd``, ``duration_ms``. :func:`_envelope_from` accepts either
shape, so usage recording, credential refresh, the auth-failure markers and
:func:`run_json`'s "returns parsed JSON" contract are one implementation rather
than two that can drift.

## What is deliberately absent

QAgent's module also carries an *agentic* path — ``--allowedTools``,
``--dangerously-skip-permissions``, ``--add-dir``, a browser harness. None of it
is ported. A knowledge build reads a clone with the CLI's default read-only
tools; it never gets a shell, which is what keeps "the hub clones arbitrary
repositories" from meaning "the hub executes them" (ADR 0007 § Consequences).
Adding a tool allowlist here is a decision that needs its own ADR.

## Sessions are explicit

QAgent's version reaches for ``SessionLocal`` and an ambient run/owner context
because its callers are worker threads with no user in scope. The hub passes
``db`` and ``owner_id`` down instead — the build worker already knows both, and
an explicit owner is what makes "this build spent *this* member's money"
checkable rather than conventional.

## Secrets

The prompt, the CLI's output and the CLI's error streams are logged at sizes and
places chosen so no credential can ride along: the credential never appears in
``cmd`` (it is on disk, referenced by ``CLAUDE_CONFIG_DIR``), and failure detail
is truncated and scrubbed before it reaches a log line or a caller's message.
"""

from __future__ import annotations

import json
import os
import queue
import re
import subprocess
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from app.config import settings
from app.logging import logger

__all__ = ["ClaudeError", "describe_event", "run_json", "run_prompt"]

#: A decoded ``stream-json`` event, handed to ``on_event`` as it arrives.
StreamEvent = dict[str, Any]
EventHandler = Callable[[StreamEvent], None]


class ClaudeError(RuntimeError):
    """The Claude CLI is unavailable, unauthenticated, or failed.

    Its ``str()`` lands in ``ProjectKnowledge.last_error`` and in the log, so
    everything interpolated into it is already truncated and scrubbed.
    """


#: Substrings (lowercased) in a failed call's output that mean the credential
#: itself is the problem, rather than the prompt or the repository.
_AUTH_ERROR_MARKERS = (
    "not logged in",
    "please run /login",
    "invalid authentication credentials",
    "failed to authenticate",
    "api error: 401",
)

_USAGE_TOKEN_KEYS = (
    "input_tokens",
    "output_tokens",
    "cache_read_input_tokens",
    "cache_creation_input_tokens",
)

#: How much of a failed call's output reaches a message. Enough to diagnose,
#: bounded so a repository's contents cannot be dumped into a database column.
_DETAIL_LIMIT = 600


# ----------------------------------------------------------------- helpers
def _resolve_model(
    db: Session, owner_id: int | None, skill: str | None = None
) -> tuple[str, str]:
    """``(model, effort)`` for one call, resolved against whoever owns the work.

    ``owner_id`` is the owner of the thing being built, not the caller — the same
    id that already decides which credential the call authenticates with — so a
    build spends the model its owner picked in Claude Settings. Nobody's choice,
    or no owner at all, falls back to ``settings.claude_model`` and the default
    effort (:mod:`app.services.model_preferences`).

    ``skill`` is accepted so the signature matches QAgent's and a per-skill map
    can be added without touching call sites — the hub runs exactly one skill
    today, so there is nothing to map.
    """
    from app.services import model_preferences

    return model_preferences.resolve_for_run(db, owner_id)


def _extract_json(text: str) -> Any:
    """Pull the first JSON object/array out of a model response."""
    fenced = re.search(r"```(?:json)?\s*(\{.*?\}|\[.*?\])\s*```", text, re.DOTALL)
    candidate = fenced.group(1) if fenced else None
    if candidate is None:
        span = re.search(r"(\{.*\}|\[.*\])", text, re.DOTALL)
        candidate = span.group(1) if span else text
    try:
        return json.loads(candidate)
    except json.JSONDecodeError as exc:
        # The offending text is NOT quoted: it is model output derived from a
        # repository's contents, and this string ends up in `last_error`.
        raise ClaudeError(f"Claude returned non-JSON output: {exc}") from exc


def _compose_system(system: str | None, skill: str | None, include_template: bool) -> str | None:
    """Merge an explicit system prompt with a skill's ``SKILL.md``."""
    if not skill:
        return system
    from app.services.skills import load_skill

    skill_text = load_skill(skill, include_template=include_template)
    if not skill_text:
        return system
    return f"{skill_text}\n\n{system}" if system else skill_text


def _resolve_cwd(cwd: str | Path | None) -> str | None:
    """An existing directory to run in, or ``None`` (inherit ours)."""
    if not cwd:
        return None
    path = Path(cwd)
    return str(path) if path.is_dir() else None


def _resolve_env(db: Session, owner_id: int | None) -> tuple[dict[str, str], str]:
    """``(env, credential_source)`` with ``CLAUDE_CONFIG_DIR`` pointed at the
    materialised credential for ``owner_id``.

    Raises:
        ClaudeError: nobody has configured a Claude credential this owner could
            run under. Phrased for the person who will read it on the row.
    """
    from app.services import claude_credentials

    resolved = claude_credentials.resolve_effective_config_dir(db, owner_id)
    if resolved is None:
        raise ClaudeError(
            "No Claude credential is configured. Upload your own in Settings, or "
            "ask an admin to configure the shared account."
        )
    config_dir, source = resolved
    return {**os.environ, "CLAUDE_CONFIG_DIR": str(config_dir)}, source


def _persist_refreshed_credential(db: Session, owner_id: int | None, env: dict[str, str]) -> None:
    """Capture a token the CLI rotated in place, so the hub stays authoritative.

    OAuth access tokens live hours and the CLI rewrites ``.credentials.json``
    whenever it refreshes one. The hub materialised that file, so unless the
    rotated value is read back the stored credential goes stale and eventually
    dies — the same failure ``PUT /credentials/claude/refreshed`` exists to
    prevent for agents (INTEGRATION.md §4).

    Best-effort by construction: credential bookkeeping must never fail the
    build it is observing, and the exception is logged **without** its content
    in case a malformed file's parser message quotes token material.
    """
    from app.services import claude_credentials

    try:
        creds_file = Path(env["CLAUDE_CONFIG_DIR"]) / ".credentials.json"
        if not creds_file.is_file():
            return
        claude_credentials.persist_refreshed_from_raw(
            db, owner_id, creds_file.read_text(encoding="utf-8")
        )
    except Exception as exc:  # noqa: BLE001 - bookkeeping never breaks a build
        logger.warning("Could not persist a refreshed Claude credential: %s", type(exc).__name__)


def _mark_credential_invalid(db: Session, owner_id: int | None) -> None:
    """Flag the effective credential expired after an auth failure, so the UI
    shows why instead of a generic build error. Never raises."""
    from app.services import claude_credentials

    try:
        row, _source = claude_credentials.resolve(db, owner_id)
        if row is not None:
            claude_credentials.mark_expired(db, row)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Could not flag the Claude credential invalid: %s", type(exc).__name__)


def _usage_from_model_usage(model_usage: Any) -> dict[str, int] | None:
    """Sum a newer CLI's per-model ``modelUsage`` into the legacy token shape."""
    if not isinstance(model_usage, dict) or not model_usage:
        return None
    totals = dict.fromkeys(_USAGE_TOKEN_KEYS, 0)
    found = False
    for stats in model_usage.values():
        if not isinstance(stats, dict):
            continue
        totals["input_tokens"] += int(stats.get("inputTokens") or stats.get("input_tokens") or 0)
        totals["output_tokens"] += int(
            stats.get("outputTokens") or stats.get("output_tokens") or 0
        )
        totals["cache_read_input_tokens"] += int(
            stats.get("cacheReadInputTokens") or stats.get("cache_read_input_tokens") or 0
        )
        totals["cache_creation_input_tokens"] += int(
            stats.get("cacheCreationInputTokens") or stats.get("cache_creation_input_tokens") or 0
        )
        found = True
    return totals if found else None


def _cost_from_model_usage(model_usage: Any) -> float | None:
    if not isinstance(model_usage, dict) or not model_usage:
        return None
    total, found = 0.0, False
    for stats in model_usage.values():
        if isinstance(stats, dict):
            cost = stats.get("costUSD", stats.get("cost_usd"))
            if isinstance(cost, (int, float)):
                total += float(cost)
                found = True
    return total if found else None


def _record_usage(
    db: Session,
    envelope: dict | None,
    *,
    model: str,
    action: str,
    wall_ms: int,
    owner_id: int | None,
    credential_source: str,
) -> None:
    """Attribute a call's tokens, cost and latency to ``owner_id``.

    ADR 0007 § Consequences: "the hub is now a place where money is spent". This
    is what makes that attributable. Best-effort — ``claude_usage.record``
    already swallows its own write errors, and this wrapper covers the parse.
    """
    try:
        from app.services import claude_usage

        env = envelope or {}
        usage = env.get("usage") or {}
        if not isinstance(usage, dict) or not any(usage.get(k) for k in _USAGE_TOKEN_KEYS):
            usage = _usage_from_model_usage(env.get("modelUsage")) or {}
        cost = env.get("total_cost_usd")
        if not isinstance(cost, (int, float)) or cost == 0:
            cost = _cost_from_model_usage(env.get("modelUsage")) or cost or 0.0
        duration = env.get("duration_ms")
        claude_usage.record(
            db,
            owner_id=owner_id,
            source="emehub",
            model=model,
            input_tokens=usage.get("input_tokens", 0),
            output_tokens=usage.get("output_tokens", 0),
            cache_read_tokens=usage.get("cache_read_input_tokens", 0),
            cache_write_tokens=usage.get("cache_creation_input_tokens", 0),
            cost_usd=cost,
            duration_ms=int(duration) if isinstance(duration, (int, float)) else wall_ms,
            action=action,
            credential_source=credential_source,
        )
    except Exception as exc:  # noqa: BLE001 - usage capture is additive
        logger.warning("Claude usage capture skipped: %s", exc)


# --------------------------------------------------------------- streaming
#: Tools whose invocation says something a human wants to read, mapped to the
#: input key that names *what* it acted on. Anything not listed still produces a
#: line ("Running <Tool>…"), it just does not try to name a target.
_TOOL_TARGET_KEY: dict[str, str] = {
    "Read": "file_path",
    "Write": "file_path",
    "Edit": "file_path",
    "NotebookRead": "notebook_path",
    "Glob": "pattern",
    "Grep": "pattern",
    "WebFetch": "url",
    "Task": "description",
}

#: Present-participle verb per tool, so the line reads as an activity.
_TOOL_VERB: dict[str, str] = {
    "Read": "Reading",
    "Write": "Writing",
    "Edit": "Editing",
    "NotebookRead": "Reading",
    "Glob": "Looking for",
    "Grep": "Searching for",
    "WebFetch": "Fetching",
    "Bash": "Running a command",
    "Task": "Delegating",
    "TodoWrite": "Planning",
}

#: The live message is a status line, not a transcript. Long before the column
#: limit, anything longer stops being readable in the UI's one row.
_MESSAGE_LIMIT = 160


def _shorten(value: str, limit: int = 72) -> str:
    """A path or pattern trimmed to something that fits a status line.

    Paths keep their **tail** — ``…/services/knowledge_service.py`` says far more
    than the first 72 characters of an absolute path ever would.
    """
    text = " ".join(str(value).split())
    if len(text) <= limit:
        return text
    return "…" + text[-(limit - 1) :]


def describe_event(event: StreamEvent) -> str | None:
    """A one-line human description of a ``stream-json`` event, or ``None``.

    ``None`` means "this event says nothing new" — most of the stream is
    tool *results* and bookkeeping, and emitting a line for those would make the
    UI flicker without informing anyone.

    Nothing here is trusted: the strings come out of a model that has just been
    reading an arbitrary repository, so every one is whitespace-collapsed and
    length-bounded. Scrubbing for credentials happens at the caller, on the way
    to the database, because that is the boundary that matters.
    """
    if not isinstance(event, dict):
        return None

    kind = event.get("type")
    if kind == "system" and event.get("subtype") == "init":
        return "Claude session started"

    if kind != "assistant":
        return None

    content = ((event.get("message") or {}).get("content")) or []
    if not isinstance(content, list):
        return None

    # A tool call is the most informative thing in the stream, so it wins over
    # any prose in the same message.
    for block in content:
        if not isinstance(block, dict) or block.get("type") != "tool_use":
            continue
        name = str(block.get("name") or "tool")
        verb = _TOOL_VERB.get(name, f"Running {name}")
        payload = block.get("input")
        target_key = _TOOL_TARGET_KEY.get(name)
        target = ""
        if target_key and isinstance(payload, dict):
            target = str(payload.get(target_key) or "")
        return f"{verb} {_shorten(target)}".strip() if target else verb

    for block in content:
        if isinstance(block, dict) and block.get("type") == "text":
            text = " ".join(str(block.get("text") or "").split())
            if text:
                return _shorten(text, _MESSAGE_LIMIT)
    return None


def _decode_event(line: str) -> StreamEvent | None:
    """One NDJSON line → an event, or ``None`` for blank/undecodable output.

    The CLI can interleave a plain-text warning with its NDJSON; a stray line is
    not a build failure, so it is skipped rather than raised on.
    """
    text = line.strip()
    if not text.startswith("{"):
        return None
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def _terminate(proc: "subprocess.Popen[str]") -> None:
    """Stop a CLI that overran its budget, and do not leave a zombie."""
    try:
        proc.kill()
        proc.wait(timeout=5)
    except Exception:  # noqa: BLE001 - teardown is best-effort by definition
        pass


def _run_blocking(
    cmd: list[str], *, cwd: str | None, env: dict[str, str], budget: int
) -> tuple[int, str, str]:
    """The original path: run to completion, then read. ``(rc, stdout, stderr)``."""
    proc = subprocess.run(  # fixed argv, no shell
        cmd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=budget,
        check=False,
        cwd=cwd,
        env=env,
    )
    return proc.returncode, (proc.stdout or "").strip(), (proc.stderr or "").strip()


def _run_streaming(
    cmd: list[str],
    *,
    cwd: str | None,
    env: dict[str, str],
    budget: int,
    on_event: EventHandler,
) -> tuple[int, str, str]:
    """Run the CLI and dispatch each NDJSON line as it arrives.

    Two pump threads, because both pipes must be drained: a full stderr buffer
    deadlocks a process whose stdout we are patiently reading. The main loop
    takes lines off a queue with a *deadline* rather than calling ``readline``
    directly, so a CLI that stops emitting entirely is still killed at ``budget``
    instead of blocking this thread forever.

    ``on_event`` is called on this thread and is never allowed to fail the run —
    a progress write that throws must not lose a build that is going fine.
    """
    proc = subprocess.Popen(  # noqa: S603 - fixed argv, no shell
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
        cwd=cwd,
        env=env,
    )
    lines: list[str] = []
    stderr_text = ""
    inbox: queue.Queue[str | None] = queue.Queue()

    def pump_stdout() -> None:
        try:
            assert proc.stdout is not None
            for line in proc.stdout:
                inbox.put(line)
        finally:
            inbox.put(None)

    def pump_stderr() -> None:
        nonlocal stderr_text
        try:
            assert proc.stderr is not None
            stderr_text = proc.stderr.read() or ""
        except Exception:  # noqa: BLE001
            pass

    readers = (
        threading.Thread(target=pump_stdout, name="claude-stdout", daemon=True),
        threading.Thread(target=pump_stderr, name="claude-stderr", daemon=True),
    )
    for reader in readers:
        reader.start()

    deadline = time.monotonic() + budget
    try:
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                _terminate(proc)
                raise subprocess.TimeoutExpired(cmd, budget)
            try:
                line = inbox.get(timeout=min(remaining, 1.0))
            except queue.Empty:
                continue
            if line is None:
                break
            lines.append(line)
            event = _decode_event(line)
            if event is None:
                continue
            try:
                on_event(event)
            except Exception as exc:  # noqa: BLE001 - progress never fails a build
                logger.warning("Claude stream handler raised: %s", type(exc).__name__)

        remaining = max(1.0, deadline - time.monotonic())
        try:
            proc.wait(timeout=remaining)
        except subprocess.TimeoutExpired:
            _terminate(proc)
            raise
    finally:
        for reader in readers:
            reader.join(timeout=2)

    return proc.returncode, "".join(lines).strip(), stderr_text.strip()


def _envelope_from(stdout_text: str) -> dict | None:
    """The result envelope, from either output format.

    ``--output-format json`` prints exactly one object, so the whole of stdout
    parses. ``stream-json`` prints one object per line and the last
    ``{"type": "result", …}`` is the same envelope — same ``result``, ``usage``,
    ``modelUsage``, ``total_cost_usd`` and ``duration_ms`` keys — so both paths
    feed identical data to usage recording and to :func:`run_json`.
    """
    if not stdout_text:
        return None
    try:
        parsed = json.loads(stdout_text)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass
    for line in reversed(stdout_text.splitlines()):
        event = _decode_event(line)
        if event is not None and event.get("type") == "result":
            return event
    return None


# -------------------------------------------------------------------- runs
def run_prompt(
    prompt: str,
    *,
    db: Session,
    owner_id: int | None,
    system: str | None = None,
    skill: str | None = None,
    include_template: bool = False,
    timeout: int | None = None,
    label: str | None = None,
    cwd: str | Path | None = None,
    on_event: EventHandler | None = None,
) -> str:
    """Run one prompt through the CLI and return its text result.

    ``cwd`` is the repository clone: running there is what lets the CLI's file
    tools read real source instead of inferring structure from metadata.

    ``on_event`` opts into the streaming invocation (module docstring): the CLI
    is asked for ``stream-json --verbose`` and every decoded event is handed to
    the callback as it arrives, so a caller can show what the model is doing
    while it does it. Everything after the subprocess — usage, credential
    refresh, auth detection, the returned string — is identical either way.

    Raises:
        ClaudeError: the CLI is missing, unauthenticated, timed out or exited
            non-zero. Every message is safe to store on a knowledge row.
    """
    system = _compose_system(system, skill, include_template)
    model, effort = _resolve_model(db, owner_id, skill)
    budget = timeout or settings.claude_timeout_s
    streaming = on_event is not None
    output_format = ["--output-format", "stream-json", "--verbose"] if streaming else [
        "--output-format",
        "json",
    ]
    cmd = [
        settings.claude_bin,
        "-p",
        prompt,
        *output_format,
        "--model",
        model,
        "--effort",
        effort,
    ]
    if system:
        cmd += ["--append-system-prompt", system]

    env, credential_source = _resolve_env(db, owner_id)
    resolved_cwd = _resolve_cwd(cwd)
    # Lengths and the resolved settings only — never the prompt, which embeds
    # project config. The model and effort are logged because they are now a
    # per-user resolution rather than a constant: this line is how you tell which
    # preference a build actually ran under.
    logger.info(
        "Claude CLI: %s (%d-char prompt, model=%s, effort=%s, timeout=%ss, %s)",
        label or skill or "call",
        len(prompt),
        model,
        effort,
        budget,
        "streaming" if streaming else "blocking",
    )

    started = time.monotonic()
    try:
        if on_event is not None:
            returncode, stdout_text, stderr_text = _run_streaming(
                cmd, cwd=resolved_cwd, env=env, budget=budget, on_event=on_event
            )
        else:
            returncode, stdout_text, stderr_text = _run_blocking(
                cmd, cwd=resolved_cwd, env=env, budget=budget
            )
    except FileNotFoundError as exc:
        raise ClaudeError(
            f"Claude CLI not found (looked for '{settings.claude_bin}'). The API "
            "image installs it; a host install needs EMEHUB_CLAUDE_BIN."
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise ClaudeError(f"Claude CLI timed out after {budget}s") from exc

    # The CLI may have rotated its own access token inside the config dir.
    _persist_refreshed_credential(db, owner_id, env)

    if returncode != 0:
        # `claude -p --output-format json` writes its failure reason to STDOUT
        # and leaves STDERR empty, so a bare exit code hides the real cause.
        combined = f"{stdout_text}\n{stderr_text}".lower()
        if any(marker in combined for marker in _AUTH_ERROR_MARKERS):
            _mark_credential_invalid(db, owner_id)
            raise ClaudeError(
                "Claude rejected the credential (expired or revoked). Upload a "
                "fresh one, then build again."
            )
        detail = (stderr_text or stdout_text or "no output")[:_DETAIL_LIMIT]
        logger.error("Claude CLI exited %s: %s", returncode, detail)
        raise ClaudeError(f"Claude CLI exited {returncode}: {detail}")

    envelope = _envelope_from(stdout_text)

    _record_usage(
        db,
        envelope,
        model=model,
        action=skill or label or "claude-cli",
        wall_ms=int((time.monotonic() - started) * 1000),
        owner_id=owner_id,
        credential_source=credential_source,
    )

    if envelope is not None and "result" in envelope:
        return str(envelope["result"])
    if streaming:
        # A stream that ended without its terminal `result` event produced no
        # answer. Returning the raw NDJSON would let `_extract_json` "succeed"
        # on the session-init event and hand the caller a knowledge base built
        # from bookkeeping.
        raise ClaudeError(
            "Claude ended without returning a result. Try the build again."
        )
    return stdout_text


def run_json(
    prompt: str,
    *,
    db: Session,
    owner_id: int | None,
    system: str | None = None,
    skill: str | None = None,
    include_template: bool = False,
    timeout: int | None = None,
    label: str | None = None,
    cwd: str | Path | None = None,
    on_event: EventHandler | None = None,
) -> Any:
    """:func:`run_prompt`, with the response parsed as JSON.

    ``on_event`` is passed straight through: the contract here — returns parsed
    JSON, records usage and cost, persists a refreshed credential, marks an
    invalid one — is unchanged by streaming, because both output formats yield
    the same envelope (module docstring).
    """
    instruction = (
        "\n\nRespond with ONLY a single valid JSON value (object or array). "
        "Do not include prose or markdown fences."
    )
    return _extract_json(
        run_prompt(
            prompt + instruction,
            db=db,
            owner_id=owner_id,
            system=system,
            skill=skill,
            include_template=include_template,
            timeout=timeout,
            label=label,
            cwd=cwd,
            on_event=on_event,
        )
    )
