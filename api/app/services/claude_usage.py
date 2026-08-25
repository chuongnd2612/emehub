"""Claude usage capture and aggregation, ``owner_id``-scoped.

Ported from QAgent's ``ai_usage_service`` and reduced to what the hub can
honestly own. QAgent records usage as a side effect of *running* the CLI; the
hub never runs it, so here the agent reports each completed call and the hub
aggregates. Everything is scoped through :func:`app.services.ownership.owned`,
so a member's spend is theirs alone and shared-credential spend
(``owner_id IS NULL``) is visible to everyone.

Windows match QAgent's contract so the two dashboards agree:

* ``requestsToday`` / ``avgLatencyMs`` — since 00:00 UTC today.
* ``costMonth`` — the current calendar month.
* ``weekTokens`` / ``breakdown`` / ``week`` / ``byModel`` — the current ISO week
  (Mon 00:00 UTC).
* ``weekResetsAt`` — next Monday 00:00 UTC.
* ``session`` — a rolling five hours; see :data:`SESSION_WINDOW`.

Every timestamp this module emits is UTC in ``%Y-%m-%dT%H:%M:%SZ`` form. There is
deliberately one convention, because two would eventually disagree by an hour and
nobody would notice which one was wrong.

What is not here, and stays not here: a percentage of plan used. This module is
told about calls after they finish, so it knows no limit to be a percentage of,
and it will not invent one from a cost. The percentages the chip shows come from
:mod:`app.services.claude_plan_limits`, which asks Claude directly using the
credential the user resolves to, and the router overlays the two. Keeping them in
separate modules keeps the seam visible: everything here is the hub's own rows,
everything there is somebody else's account.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.logging import logger
from app.models.claude_usage import ClaudeUsage
from app.services.ownership import owned

__all__ = ["record", "stats"]


def record(
    db: Session,
    *,
    owner_id: int | None,
    source: str = "emehub",
    model: str = "",
    input_tokens: int = 0,
    output_tokens: int = 0,
    cache_read_tokens: int = 0,
    cache_write_tokens: int = 0,
    cost_usd: float = 0.0,
    duration_ms: int = 0,
    action: str = "",
    credential_source: str = "",
    external_ref: str = "",
    ts: datetime | None = None,
) -> ClaudeUsage | None:
    """Append one usage row. Best-effort — never raises into the caller.

    Usage capture must not be able to fail the work it is observing, so a
    write error is logged and swallowed exactly like the audit trail.
    """
    row = ClaudeUsage(
        ts=ts or datetime.now(timezone.utc),
        source=(source or "emehub")[:32],
        external_ref=(external_ref or "")[:120],
        model=(model or "")[:64],
        input_tokens=max(int(input_tokens or 0), 0),
        output_tokens=max(int(output_tokens or 0), 0),
        cache_read_tokens=max(int(cache_read_tokens or 0), 0),
        cache_write_tokens=max(int(cache_write_tokens or 0), 0),
        cost_usd=max(float(cost_usd or 0.0), 0.0),
        duration_ms=max(int(duration_ms or 0), 0),
        action=(action or "")[:120],
        credential_source=(credential_source or "")[:16],
        owner_id=owner_id,
    )
    try:
        db.add(row)
        db.commit()
        db.refresh(row)
        return row
    except Exception as exc:  # noqa: BLE001 - usage capture never breaks a call
        logger.warning("Claude usage record failed: %s", exc)
        db.rollback()
        return None


#: How long a "session" lasts for the hub.
#:
#: The hub has no session of its own — it never runs the CLI, so nothing tells it
#: where one begins. Five hours is not a guess: it is Claude's own usage window,
#: and it is the window QAgent reports against
#: (``q-agent`` ``claude_usage_reader._SESSION_WINDOW``). Matching it keeps the two
#: chips describing the same thing rather than two different five-hour-ish periods.
SESSION_WINDOW = timedelta(hours=5)


def _iso_z(value: datetime) -> str:
    """UTC → ``2026-08-25T14:00:00Z``. The module's only timestamp format."""
    return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _windows(now: datetime) -> tuple[datetime, datetime, datetime, str, datetime]:
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    month = today.replace(day=1)
    week = today - timedelta(days=today.weekday())
    # Mon=0 → 7, so this is always the *next* Monday, never today.
    resets = _iso_z(today + timedelta(days=7 - now.weekday()))
    return today, month, week, resets, now - SESSION_WINDOW


_TOKEN_COLUMNS = (
    ClaudeUsage.input_tokens,
    ClaudeUsage.output_tokens,
    ClaudeUsage.cache_read_tokens,
    ClaudeUsage.cache_write_tokens,
)


def _window(db: Session, user, since: datetime) -> tuple[list[int], int, float]:
    """Token sums (in the order of :data:`_TOKEN_COLUMNS`), requests and cost."""
    row = (
        owned(
            db.query(
                *(func.sum(column) for column in _TOKEN_COLUMNS),
                func.count(ClaudeUsage.id),
                func.sum(ClaudeUsage.cost_usd),
            ),
            ClaudeUsage,
            user,
        )
        .filter(ClaudeUsage.ts >= since)
        .one()
    )
    return [int(value or 0) for value in row[:4]], int(row[4] or 0), float(row[5] or 0.0)


def _session_resets_at(db: Session, user, since: datetime, now: datetime) -> str:
    """When the current five-hour window closes, *estimated from the hub's rows*.

    Anchored to the *earliest call still inside the window*, not to a clock
    boundary — the same rule QAgent applies, and the reason its reset time reads
    as an odd number of minutes past the hour rather than on it. With no calls in
    the window there is nothing to anchor to, so a fresh window starts now.

    Since #212 this is the **fallback**, not the answer. Claude owns the boundary
    and states it, and when :mod:`app.services.claude_plan_limits` gets a
    ``resets_at`` the router replaces this value with it — so what ships is an
    estimate of somebody else's boundary, reached for only when that somebody
    did not say. The anchoring above still describes it exactly; it is the
    *precedence* that changed, and callers see one time either way, never both.
    """
    earliest = (
        owned(db.query(func.min(ClaudeUsage.ts)), ClaudeUsage, user)
        .filter(ClaudeUsage.ts >= since)
        .scalar()
    )
    if earliest is None:
        return _iso_z(now + SESSION_WINDOW)
    if earliest.tzinfo is None:
        earliest = earliest.replace(tzinfo=timezone.utc)
    return _iso_z(earliest + SESSION_WINDOW)


def _by_model(db: Session, user, since: datetime) -> list[dict[str, Any]]:
    """Per-model tokens and cost across ``since``, dearest first.

    ``model`` is whatever the reporting agent sent — including ``""`` when it sent
    nothing, which SQL groups into a single bucket on its own. The empty string
    travels as-is rather than being relabelled here: the service reports what the
    table holds, and naming the anonymous bucket is the UI's job.
    """
    rows = (
        owned(
            db.query(
                ClaudeUsage.model,
                *(func.sum(column) for column in _TOKEN_COLUMNS),
                func.sum(ClaudeUsage.cost_usd),
            ),
            ClaudeUsage,
            user,
        )
        .filter(ClaudeUsage.ts >= since)
        .group_by(ClaudeUsage.model)
        .all()
    )
    out = [
        {
            "model": row[0] or "",
            "tokens": sum(int(value or 0) for value in row[1:5]),
            "costUsd": round(float(row[5] or 0.0), 4),
        }
        for row in rows
    ]
    # Dearest first, then by tokens so a run of zero-cost models still has a
    # stable order rather than whatever the database happened to return.
    out.sort(key=lambda entry: (entry["costUsd"], entry["tokens"]), reverse=True)
    return out


def stats(db: Session, user, now: datetime | None = None) -> dict[str, Any]:
    """Aggregate the usage ``user`` may see. ``user=None`` yields zeroes.

    Fails closed through :func:`app.services.ownership.owned`: an absent user
    sees nothing rather than everything.
    """
    reference = now or datetime.now(timezone.utc)
    today, month, week, resets, session_since = _windows(reference)

    requests_today, avg_latency = (
        owned(
            db.query(func.count(ClaudeUsage.id), func.avg(ClaudeUsage.duration_ms)),
            ClaudeUsage,
            user,
        )
        .filter(ClaudeUsage.ts >= today)
        .one()
    )
    cost_month = (
        owned(db.query(func.sum(ClaudeUsage.cost_usd)), ClaudeUsage, user)
        .filter(ClaudeUsage.ts >= month)
        .scalar()
    )

    week_tokens, week_requests, week_cost = _window(db, user, week)
    inp, out, cache_read, cache_write = week_tokens
    session_tokens, session_requests, session_cost = _window(db, user, session_since)

    return {
        "requestsToday": int(requests_today or 0),
        "avgLatencyMs": int(round(avg_latency or 0)),
        "costMonth": round(float(cost_month or 0.0), 4),
        "weekTokens": inp + out + cache_read + cache_write,
        "weekResetsAt": resets,
        "breakdown": {
            "input": inp,
            "output": out,
            "cacheRead": cache_read,
            "cacheWrite": cache_write,
        },
        "session": {
            "tokens": sum(session_tokens),
            "requests": session_requests,
            "costUsd": round(session_cost, 4),
            "resetsAt": _session_resets_at(db, user, session_since, reference),
        },
        "week": {
            "tokens": inp + out + cache_read + cache_write,
            "requests": week_requests,
            "costUsd": round(week_cost, 4),
            "resetsAt": resets,
        },
        "byModel": _by_model(db, user, week),
    }
