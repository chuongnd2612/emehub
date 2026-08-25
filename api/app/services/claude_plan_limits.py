"""The plan-limit percentages behind Claude's own ``/usage`` view.

``claude_usage`` aggregates what agents *report*: tokens, cost, requests. That is
spend in absolute terms, and it knows no limit to be a percentage of. This module
supplies the missing denominator — the two numbers the CLI shows as
``Current session: N% used`` and ``Current week (all models): N% used`` — for the
credential a given user's runs actually authenticate with.

## Where they come from, and where they don't

Not from the CLI. ``/usage`` is a rendering of an authenticated HTTP call, and we
can make that call ourselves: :data:`_USAGE_URL` with the credential's OAuth
access token and the :data:`_USAGE_BETA` beta header returns the windows as JSON
(``five_hour`` → session, ``seven_day`` → week), each with a ``utilization``
percentage and an authoritative ``resets_at``.

QAgent's ``claude_usage_reader`` prefers this endpoint too, but keeps a fallback
that spawns ``claude``, pipes ``/usage`` to its stdin and regex-parses the TUI.
It needs one: it reads credentials off disk and can come up empty. **The hub does
not, and deliberately has none.** Its credentials live in Postgres and
:func:`app.services.claude_credentials.resolve_material` already decrypts the
right one per user, so there is no case where scraping succeeds and this call
fails — the scrape would only be reading a materialised copy of the same token.
Buying that non-coverage would cost a plaintext write to the workspace volume
(the one thing ADR 0007 confines to knowledge builds), a TUI subprocess on a
header-popover read, and a parser aimed at output that changes between CLI
releases. An honest "unknown" is worth more than any of that.

## The token

It is decrypted into a local, sent as one ``Authorization`` header, and dropped
when the frame exits. It reaches no file, no log line, no exception message and
no response body — callers of this module get three scalars per window. The
single decrypt path stays the one in ``claude_credentials``; this module adds a
caller to it, not a second way in.

## Failure

Every failure is the same answer: ``-1``, meaning unknown, and a status of
``"unavailable"``. No credential, an expired token, a refused request, an
unparseable payload — none of them raise, and none of them fabricate a number.
Expired tokens are skipped rather than refreshed: rotating a stored credential
from a background thread on a popover read is not this module's business, and the
CLI rewrites the row on its next real run anyway.

## Cost

The fetch is an outbound network call and the caller is a popover. So it is
cached for :data:`_TTL_S` and refreshed on a background thread — reads never
block on the network, and the first read of a cold entry says ``"loading"``
rather than waiting. The cache is keyed by **credential row id, not user id**:
two users on the shared credential are asking about the same account, so they
share one entry and one call. That is also what keeps ownership scoping intact by
construction — a user is only ever handed the entry for the credential they
resolve to, so there is no key under which one user's plan usage could be served
to another.
"""

from __future__ import annotations

import json
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from typing import Any

from app.logging import logger
from app.services import claude_credentials

__all__ = [
    "STATUS_LOADING",
    "STATUS_READY",
    "STATUS_UNAVAILABLE",
    "UNKNOWN_PCT",
    "limits_for",
]

#: A percentage nobody could tell us. The UI falls back to cost when it sees it.
UNKNOWN_PCT = -1

#: The endpoint the CLI's own ``/usage`` view consumes.
_USAGE_URL = "https://api.anthropic.com/api/oauth/usage"
_USAGE_BETA = "oauth-2025-04-20"
_TIMEOUT_S = 15

#: How long a fetched result stands before a refresh is kicked off. QAgent uses
#: the same 180s, and for the same reason: the numbers move in percentage points
#: over minutes, and the popover is opened far more often than that.
_TTL_S = 180.0

#: Status values. ``loading`` is only ever the *first* read of a cold entry;
#: after that a stale entry keeps serving while the refresh runs behind it.
STATUS_LOADING = "loading"
STATUS_READY = "ready"
STATUS_UNAVAILABLE = "unavailable"

#: ``credential_row_id -> (monotonic_ts, parsed | None)``. Small and bounded by
#: the number of credentials, which is bounded by the number of users.
_cache: dict[int, tuple[float, dict[str, Any] | None]] = {}
#: Row ids with a refresh in flight, so a burst of reads makes one call.
_in_flight: set[int] = set()
_lock = threading.Lock()


def _iso_z(value: datetime) -> str:
    """UTC → ``2026-08-25T19:10:00Z`` — ``claude_usage``'s one timestamp format.

    The endpoint answers with an offset and microseconds
    (``2026-08-25T19:10:00.445058+00:00``). Two conventions in one payload would
    eventually disagree by an hour and nobody would notice which was wrong, so
    upstream's shape is normalised here rather than travelling onward.
    """
    return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_reset(raw: Any) -> str:
    """An upstream ``resets_at`` as a hub timestamp, or ``""`` if unusable."""
    try:
        return _iso_z(datetime.fromisoformat(str(raw)))
    except (TypeError, ValueError):
        return ""


def _window(raw: Any) -> dict[str, Any]:
    """One window of the payload as ``{pctUsed, resetsAt}``, or ``{}``.

    Empty when the window is absent or carries no ``utilization`` — the account
    has no limit of that kind, which is not the same as a limit of zero. Only the
    keys that are genuinely known are returned, so the merge in the router
    overlays a real reset time and leaves the derived one alone otherwise.
    """
    if not isinstance(raw, dict) or raw.get("utilization") is None:
        return {}
    try:
        out: dict[str, Any] = {"pctUsed": int(round(float(raw["utilization"])))}
    except (TypeError, ValueError):
        return {}
    resets_at = _parse_reset(raw.get("resets_at"))
    if resets_at:
        out["resetsAt"] = resets_at
    return out


def _parse(payload: Any) -> dict[str, Any] | None:
    """The payload's two relevant windows, or ``None`` if neither is usable.

    The response also carries per-model weeklies, spend, extra-usage and a
    handful of internally-named fields. None of them are read: the chip has two
    rows, and inventing a third from a key whose meaning we would be guessing at
    is how a dashboard starts lying.
    """
    if not isinstance(payload, dict):
        return None
    session = _window(payload.get("five_hour"))
    week = _window(payload.get("seven_day"))
    if not session and not week:
        return None
    return {"session": session, "week": week}


def _live_token(material: dict) -> str | None:
    """The OAuth access token from decrypted credential material, if still live.

    ``None`` for a malformed blob, a missing token, or one that has expired — an
    expired token would earn a 401, and asking for one is a slower way to learn
    what ``expiresAt`` already says.
    """
    try:
        oauth = json.loads(material["credentials"]).get("claudeAiOauth")
    except (KeyError, TypeError, ValueError):
        return None
    if not isinstance(oauth, dict):
        return None
    token = oauth.get("accessToken")
    if not token:
        return None
    try:
        expires_ms = float(oauth.get("expiresAt") or 0)
    except (TypeError, ValueError):
        return None
    if time.time() * 1000 >= expires_ms:
        return None
    return str(token)


def _fetch(token: str) -> dict[str, Any] | None:
    """GET the usage endpoint with ``token``, parsed. ``None`` on any failure.

    The token is in the request headers and nowhere else. The log line names the
    exception's type and, for an HTTP error, its status — never the request, the
    headers, or the body, any of which could carry it back out.
    """
    request = urllib.request.Request(  # noqa: S310 - fixed https URL
        _USAGE_URL,
        headers={"Authorization": f"Bearer {token}", "anthropic-beta": _USAGE_BETA},
    )
    try:
        with urllib.request.urlopen(request, timeout=_TIMEOUT_S) as response:  # noqa: S310
            payload = json.load(response)
    except urllib.error.HTTPError as exc:
        logger.warning("Claude plan-limit read refused: HTTP {}", exc.code)
        return None
    except Exception as exc:  # noqa: BLE001 - a hiccup here is "unknown", not a 500
        logger.warning("Claude plan-limit read failed: {}", type(exc).__name__)
        return None
    return _parse(payload)


def _refresh(owner_id: int | None, row_id: int) -> None:
    """Fetch ``row_id``'s limits and cache them. Runs on a background thread.

    Opens its own session — the request that triggered it has very likely
    finished, and its session with it. It re-resolves first and abandons the
    refresh if ``owner_id`` no longer points at ``row_id``: the credential can be
    replaced between the read that scheduled this and the thread that runs it,
    and caching the new account's percentages under the old account's key is
    exactly the cross-account leak the row-id keying exists to prevent.

    Whatever happens, the entry is written and the in-flight mark cleared, so a
    failure caches "unknown" for a TTL instead of retrying on every read.
    """
    from app.db import SessionLocal

    parsed: dict[str, Any] | None = None
    try:
        db = SessionLocal()
        try:
            row, _source = claude_credentials.resolve(db, owner_id)
            material = (
                claude_credentials.resolve_material(db, owner_id)
                if row is not None and row.id == row_id
                else None
            )
        finally:
            db.close()
        if material is not None:
            token = _live_token(material)
            if token is not None:
                parsed = _fetch(token)
    except Exception as exc:  # noqa: BLE001 - a background thread must not die loud
        logger.warning("Claude plan-limit refresh failed: {}", type(exc).__name__)
    finally:
        with _lock:
            _cache[row_id] = (time.monotonic(), parsed)
            _in_flight.discard(row_id)


def limits_for(db, user) -> tuple[dict[str, Any] | None, str]:
    """``(parsed | None, status)`` for the credential ``user`` resolves to.

    Never raises and never blocks: a cold entry returns ``(None, "loading")`` and
    schedules the fetch, a stale one serves its last value while the refresh runs
    behind it. ``user`` without a credential — or ``None`` — is
    ``(None, "unavailable")``, which is the same answer as a failed fetch,
    because from the chip's side it is the same fact: no percentage to show.

    ``parsed`` is ``{"session": {...}, "week": {...}}`` where each window carries
    ``pctUsed`` and, when upstream gave one, ``resetsAt``. A window may be empty.
    """
    owner_id = getattr(user, "id", None)
    if owner_id is None:
        return None, STATUS_UNAVAILABLE
    try:
        row, _source = claude_credentials.resolve(db, owner_id)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Claude plan-limit resolve failed: {}", type(exc).__name__)
        return None, STATUS_UNAVAILABLE
    if row is None:
        return None, STATUS_UNAVAILABLE

    now = time.monotonic()
    with _lock:
        entry = _cache.get(row.id)
        if (entry is None or now - entry[0] >= _TTL_S) and row.id not in _in_flight:
            _in_flight.add(row.id)
            threading.Thread(
                target=_refresh, args=(owner_id, row.id), daemon=True
            ).start()
    if entry is None:
        return None, STATUS_LOADING
    parsed = entry[1]
    return parsed, (STATUS_READY if parsed else STATUS_UNAVAILABLE)
