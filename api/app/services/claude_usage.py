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
* ``weekTokens`` / ``breakdown`` — the current ISO week (Mon 00:00 UTC).
* ``weekResetsAt`` — next Monday 00:00 UTC.
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


def _windows(now: datetime) -> tuple[datetime, datetime, datetime, str]:
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    month = today.replace(day=1)
    week = today - timedelta(days=today.weekday())
    # Mon=0 → 7, so this is always the *next* Monday, never today.
    resets = (today + timedelta(days=7 - now.weekday())).strftime("%Y-%m-%dT%H:%M:%SZ")
    return today, month, week, resets


def stats(db: Session, user, now: datetime | None = None) -> dict[str, Any]:
    """Aggregate the usage ``user`` may see. ``user=None`` yields zeroes.

    Fails closed through :func:`app.services.ownership.owned`: an absent user
    sees nothing rather than everything.
    """
    reference = now or datetime.now(timezone.utc)
    today, month, week, resets = _windows(reference)

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
    totals = (
        owned(
            db.query(
                func.sum(ClaudeUsage.input_tokens),
                func.sum(ClaudeUsage.output_tokens),
                func.sum(ClaudeUsage.cache_read_tokens),
                func.sum(ClaudeUsage.cache_write_tokens),
            ),
            ClaudeUsage,
            user,
        )
        .filter(ClaudeUsage.ts >= week)
        .one()
    )
    inp, out, cache_read, cache_write = (int(v or 0) for v in totals)

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
    }
