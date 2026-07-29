"""Claude Code CLI integration — the one-shot JSON path, and nothing else.

ADR 0007 lets the hub build the shared artefacts it already owns the inputs for.
That is one job (``project-bootstrap``) and one invocation shape::

    claude -p "<prompt>" --output-format json --model <model>
           --append-system-prompt "<SKILL.md>"

run in the repository clone's directory, under a ``CLAUDE_CONFIG_DIR`` holding
the materialised credential.

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
import re
import subprocess
import time
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from app.config import settings
from app.logging import logger

__all__ = ["ClaudeError", "run_json", "run_prompt"]


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
def _resolve_model(skill: str | None = None) -> str:
    """The model a call runs on.

    ``skill`` is accepted so the signature matches QAgent's and a per-skill map
    can be added without touching call sites — the hub runs exactly one skill
    today, so there is nothing to map.
    """
    return settings.claude_model


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
) -> str:
    """Run one prompt through the CLI and return its text result.

    ``cwd`` is the repository clone: running there is what lets the CLI's file
    tools read real source instead of inferring structure from metadata.

    Raises:
        ClaudeError: the CLI is missing, unauthenticated, timed out or exited
            non-zero. Every message is safe to store on a knowledge row.
    """
    system = _compose_system(system, skill, include_template)
    model = _resolve_model(skill)
    budget = timeout or settings.claude_timeout_s
    cmd = [settings.claude_bin, "-p", prompt, "--output-format", "json", "--model", model]
    if system:
        cmd += ["--append-system-prompt", system]

    env, credential_source = _resolve_env(db, owner_id)
    resolved_cwd = _resolve_cwd(cwd)
    # Lengths and the model only — never the prompt, which embeds project config.
    logger.info(
        "Claude CLI: %s (%d-char prompt, model=%s, timeout=%ss)",
        label or skill or "call",
        len(prompt),
        model,
        budget,
    )

    started = time.monotonic()
    try:
        proc = subprocess.run(  # fixed argv, no shell
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=budget,
            check=False,
            cwd=resolved_cwd,
            env=env,
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

    stdout_text = (proc.stdout or "").strip()
    stderr_text = (proc.stderr or "").strip()

    if proc.returncode != 0:
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
        logger.error("Claude CLI exited %s: %s", proc.returncode, detail)
        raise ClaudeError(f"Claude CLI exited {proc.returncode}: {detail}")

    envelope: dict | None = None
    try:
        parsed = json.loads(stdout_text)
        if isinstance(parsed, dict):
            envelope = parsed
    except json.JSONDecodeError:
        pass

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
) -> Any:
    """:func:`run_prompt`, with the response parsed as JSON."""
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
        )
    )
