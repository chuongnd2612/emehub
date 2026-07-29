"""Claude CLI credentials — storage, parsing, and the own → shared → none rule.

This is the one secret the hub deliberately hands out (CLAUDE.md › Security
rules; INTEGRATION.md §4), so the module is written around a single invariant:

    **Exactly one function returns credential material —
    :func:`resolve_material`. Everything else returns metadata.**

:func:`status_for` and :func:`meta_for` build their output field by field from
the parsed metadata columns; neither ever touches ``row.credentials``. There is
no "include the token" flag to get wrong, and no code path that logs the blob,
truncated or otherwise — the plaintext exists only as a local in
:func:`resolve_material` and :func:`_persist_if_newer`.

Storage is via :mod:`app.crypto` only (the ``enc::v1:`` envelope over
``EMEHUB_ENCRYPTION_KEY``). The JWT secret must never appear here — ADR 0005.

## Materialisation (ADR 0007)

The hub *does* now write the credential to disk, for one job only: running
``project-bootstrap`` through the Claude CLI during a knowledge build. That is
what :func:`materialize` and :func:`resolve_effective_config_dir` are for. Two
properties keep it honest:

* the file is written **only** under the workspace volume, in an owner-scoped
  ``claude-config`` directory (:mod:`app.services.workspace_scope`), and both
  the directory and the file are chmod'ed to the owning process alone;
* it is still not *returned* by anything. :func:`resolve_material` remains the
  one function that hands credential material to a caller.

``emehub-workspace`` therefore holds plaintext credential material for the
duration of a build — ADR 0007 § Consequences says so explicitly, and it is why
that volume is not something to copy casually.

## Parsing

:func:`parse_credentials` mirrors ``app/src/data/credentials.ts`` exactly, so the
SPA and the API accept and reject the same files: the ``claudeAiOauth`` object
(or ``claude_ai_oauth``, or the bare root), ``accessToken``/``access_token``
required, ``expiresAt``/``expires_at`` as epoch ms, ``scopes`` defaulting to
``["user:inference"]`` and ``subscriptionType``/``subscription`` defaulting to
``"Claude account"``.

## Expiry is not death (issue #63)

A Claude OAuth *access* token lives hours, so a real ``.credentials.json`` is
past its ``expiresAt`` almost immediately. It also carries a **refresh token**,
and the CLI renews the access token from it on the next run without anyone
touching the hub. Deriving ``expired`` from the timestamp alone therefore turned
essentially every credential in the workspace red for no reason.

So the hub tracks *whether* a refresh token is present — one boolean,
``ClaudeCredentials.has_refresh_token``; **never the token, which stays inside
the encrypted blob** — and an elapsed expiry with a refresh token derives to
:data:`~app.models.claude_credentials.STATUS_REFRESHABLE` instead. The
authoritative "this does not work" signal is unchanged: the stored
``expired`` status that ``claude_cli._mark_credential_invalid`` writes when the
CLI really rejects the credential, and that still wins over everything.
"""

from __future__ import annotations

import json
import stat
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from app import crypto
from app.db import utcnow
from app.models.claude_credentials import (
    STATUS_ACTIVE,
    STATUS_EXPIRED,
    STATUS_EXPIRING,
    STATUS_REFRESHABLE,
    ClaudeCredentials,
)

__all__ = [
    "ClaudeCredentialsError",
    "INVALID_CREDENTIAL_MESSAGE",
    "ParsedCredential",
    "backfill_refresh_flag",
    "days_left",
    "delete_own",
    "delete_shared",
    "derived_status",
    "get_own",
    "get_shared",
    "mark_expired",
    "materialize",
    "meta_for",
    "parse_credentials",
    "persist_refreshed_from_raw",
    "resolve",
    "resolve_effective_config_dir",
    "resolve_material",
    "set_preferred_mode",
    "status_for",
    "status_of",
    "upsert_own",
    "upsert_shared",
    "verify",
]

#: Copy is final — the same string the SPA shows for an unparseable file
#: (``INVALID_CREDENTIAL_TOAST.body`` in ``app/src/data/credentials.ts``).
INVALID_CREDENTIAL_MESSAGE = "Expected a claudeAiOauth token object"

#: The scope the CLI always has; used when the file omits ``scopes``.
DEFAULT_SCOPES = ["user:inference"]
DEFAULT_SUBSCRIPTION = "Claude account"

MODE_OWN = "own"
MODE_SHARED = "shared"
MODE_NONE = "none"

_MS_PER_DAY = 86_400_000


class ClaudeCredentialsError(ValueError):
    """A credential the hub will not store — a 400 to the caller.

    The message never quotes the offending content: a malformed
    ``.credentials.json`` is still a file full of token material.
    """


@dataclass(frozen=True)
class ParsedCredential:
    """What the hub reads out of a ``.credentials.json``. Never persisted whole."""

    #: Present so validation can require it. **Never stored, returned or logged**
    #: from this object — only the encrypted original blob is persisted.
    token: str
    expires_at_ms: int | None = None
    scopes: list[str] = field(default_factory=lambda: list(DEFAULT_SCOPES))
    subscription_type: str = DEFAULT_SUBSCRIPTION
    #: Whether the file carried a ``refreshToken``. **The presence, not the
    #: token** — the refresh token is deliberately never lifted out of the blob,
    #: not even onto this transient object, so there is no field anywhere that
    #: could be logged or persisted by accident.
    has_refresh_token: bool = False

    @property
    def expires_at(self) -> datetime | None:
        if self.expires_at_ms is None:
            return None
        try:
            return datetime.fromtimestamp(self.expires_at_ms / 1000, tz=timezone.utc)
        except (ValueError, OverflowError, OSError):
            return None


# ------------------------------------------------------------------ parsing
def _as_record(value: Any) -> dict | None:
    return value if isinstance(value, dict) else None


def _as_string(value: Any) -> str | None:
    return value if isinstance(value, str) and value else None


def _as_epoch_ms(value: Any) -> int | None:
    """A finite epoch-ms number, or a string holding one. ``bool`` is not a number."""
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return int(value) if value == value and abs(value) != float("inf") else None
    if isinstance(value, str):
        try:
            parsed = float(value)
        except ValueError:
            return None
        if parsed != parsed or abs(parsed) == float("inf"):
            return None
        return int(parsed)
    return None


def parse_credentials(raw: str) -> ParsedCredential:
    """Parse + validate the text of a ``.credentials.json``.

    Mirrors ``parseCredentialJson`` in ``app/src/data/credentials.ts`` so a file
    the SPA accepts is a file the API accepts. Raises
    :class:`ClaudeCredentialsError` on malformed JSON, a non-object root, or a
    missing/empty access token — everything else is optional and defaulted.
    """
    try:
        parsed = json.loads(raw)
    except (json.JSONDecodeError, TypeError) as exc:
        # Deliberately not `from exc`-ing the decoder's message into the detail:
        # keep one fixed string so nothing derived from the file can escape.
        raise ClaudeCredentialsError(INVALID_CREDENTIAL_MESSAGE) from exc

    root = _as_record(parsed)
    if root is None:
        raise ClaudeCredentialsError(INVALID_CREDENTIAL_MESSAGE)

    source = (
        _as_record(root.get("claudeAiOauth"))
        or _as_record(root.get("claude_ai_oauth"))
        or root
    )

    token = _as_string(source.get("accessToken")) or _as_string(source.get("access_token"))
    if not token:
        raise ClaudeCredentialsError(INVALID_CREDENTIAL_MESSAGE)

    expires_at_ms = _as_epoch_ms(source.get("expiresAt"))
    if expires_at_ms is None:
        expires_at_ms = _as_epoch_ms(source.get("expires_at"))

    raw_scopes = source.get("scopes")
    scopes = (
        [s for s in raw_scopes if isinstance(s, str)] if isinstance(raw_scopes, list) else []
    )
    if not scopes:
        scopes = list(DEFAULT_SCOPES)

    subscription = (
        _as_string(source.get("subscriptionType"))
        or _as_string(source.get("subscription"))
        or DEFAULT_SUBSCRIPTION
    )

    # Presence only. `_as_string` is deliberately the last thing that touches
    # this value — it is converted straight to a bool and the string is dropped.
    has_refresh = bool(
        _as_string(source.get("refreshToken")) or _as_string(source.get("refresh_token"))
    )

    return ParsedCredential(
        token=token,
        expires_at_ms=expires_at_ms,
        scopes=scopes,
        subscription_type=subscription,
        has_refresh_token=has_refresh,
    )


# ------------------------------------------------------------------ expiry
def days_left(expires_at: datetime | None, now: datetime | None = None) -> int | None:
    """Whole days until ``expires_at``; ``None`` when the token never expires.

    Same arithmetic as ``daysLeftFrom`` in the frontend data layer.
    """
    if expires_at is None:
        return None
    reference = now or utcnow()
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    return round((expires_at - reference).total_seconds() * 1000 / _MS_PER_DAY)


def status_of(days: int | None) -> str:
    """The handoff's derived-status rule, verbatim (``credentialStatus``)."""
    if days is None:
        return STATUS_ACTIVE
    if days < 0:
        return STATUS_EXPIRED
    if days <= 2:
        return STATUS_EXPIRING
    return STATUS_ACTIVE


def has_elapsed(expires_at: datetime | None, now: datetime | None = None) -> bool:
    """Whether ``expires_at`` is strictly in the past.

    Not ``days_left(...) < 0``: ``days_left`` rounds, so a token that lapsed
    three hours ago reports ``0`` days and would read as merely *expiring*. The
    refresh rule below has to know the difference — three hours past expiry with
    a refresh token on file is the single most common state a real
    ``.credentials.json`` is ever in.
    """
    if expires_at is None:
        return False
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    return expires_at < (now or utcnow())


def derived_status(row: ClaudeCredentials, now: datetime | None = None) -> str:
    """Effective status, in strict precedence order:

    1. **the stored flag.** A row the CLI has actually rejected
       (``claude_cli._mark_credential_invalid`` → :func:`mark_expired`) stays
       ``expired`` whatever the timestamps say. That is the only signal the hub
       has that a credential *does not work*, so nothing derived may override it.
    2. **elapsed + a refresh token on file** → :data:`STATUS_REFRESHABLE`. The
       access token is genuinely past its expiry, but the CLI refreshes it on
       the next run, so this is not a credential anyone needs to re-upload.
    3. otherwise :func:`status_of`, the handoff's rule, verbatim. In particular
       ``expired`` is derived from the timestamp **only when there is no refresh
       token** — which is the fix for issue #63.

    ``has_refresh_token`` may still be NULL on a row nobody has read since the
    column landed; NULL is treated as "no refresh token" here, and
    :func:`backfill_refresh_flag` resolves it for good on the next read.
    """
    if row.status == STATUS_EXPIRED:
        return STATUS_EXPIRED
    if row.has_refresh_token and has_elapsed(row.expires_at, now):
        return STATUS_REFRESHABLE
    return status_of(days_left(row.expires_at, now))


def backfill_refresh_flag(db: Session, row: ClaudeCredentials | None) -> bool:
    """Resolve ``row.has_refresh_token`` when it is still NULL. Returns the flag.

    The column was added after rows existed, and the only place the answer lives
    is inside the encrypted blob. Decrypting the whole table inside an Alembic
    migration would make the deploy depend on ``EMEHUB_ENCRYPTION_KEY`` being
    correct at upgrade time and would fail wholesale if it were not — so the
    backfill happens here instead, per row, on first read.

    **Exactly once per row**: the write flips NULL to a real boolean, and every
    later call short-circuits before touching :mod:`app.crypto`. An
    undecryptable or unparseable blob resolves to ``False`` rather than staying
    NULL, so a broken row cannot make this decrypt on every request forever.

    **Only the boolean is written.** The plaintext exists as a local for the
    length of one parse and the refresh token is never lifted out of it.
    """
    if row is None:
        return False
    if row.has_refresh_token is not None:
        return bool(row.has_refresh_token)

    present = False
    plaintext = crypto.decrypt(row.credentials)
    if plaintext:
        try:
            present = parse_credentials(plaintext).has_refresh_token
        except ClaudeCredentialsError:
            present = False

    row.has_refresh_token = present
    db.commit()
    return present


# ------------------------------------------------------------------ lookups
def get_own(db: Session, owner_id: int | None) -> ClaudeCredentials | None:
    """The given user's own credential row, or ``None``."""
    if owner_id is None:
        return None
    return (
        db.query(ClaudeCredentials).filter(ClaudeCredentials.owner_id == owner_id).first()
    )


def get_shared(db: Session) -> ClaudeCredentials | None:
    """The single shared credential row (``owner_id IS NULL``), or ``None``."""
    return (
        db.query(ClaudeCredentials).filter(ClaudeCredentials.owner_id.is_(None)).first()
    )


def _own_yields_to_shared(db: Session, own: ClaudeCredentials | None) -> bool:
    """True when the user has their own credential but prefers the shared one
    *and* a shared one exists. ``prefer_shared`` with nothing to fall back to is
    ignored, so a user is never left with no credential at all."""
    return own is not None and own.prefer_shared and get_shared(db) is not None


def resolve(db: Session, owner_id: int | None) -> tuple[ClaudeCredentials | None, str]:
    """The credential ``owner_id`` should run with, and where it came from.

    Precedence: **own → shared → none** (ROADMAP Phase 3), with ``prefer_shared``
    skipping an existing own credential. Returns ``(row, "own" | "shared")`` or
    ``(None, "none")``. Metadata only — see :func:`resolve_material` for the
    material itself.
    """
    own = get_own(db, owner_id)
    if own is not None and not _own_yields_to_shared(db, own):
        return own, MODE_OWN
    shared = get_shared(db)
    if shared is not None:
        return shared, MODE_SHARED
    return None, MODE_NONE


def resolve_material(db: Session, owner_id: int | None) -> dict | None:
    """**The only function in the hub that returns credential material.**

    Decrypts the resolved row's ``enc::v1:`` envelope and returns the raw
    ``.credentials.json`` text alongside its metadata, or ``None`` when the user
    has no credential at all. Its single caller is
    ``GET /credentials/claude/resolve``, which audits every call
    (INTEGRATION.md §4).

    Raises :class:`ClaudeCredentialsError` when the stored blob does not
    authenticate under the current key — an unreadable credential is an error,
    never silently the empty string or the ciphertext.
    """
    row, source = resolve(db, owner_id)
    if row is None:
        return None
    plaintext = crypto.decrypt(row.credentials)
    if plaintext is None:
        raise ClaudeCredentialsError(
            "stored Claude credential could not be decrypted with the current key"
        )
    backfill_refresh_flag(db, row)
    return {"source": source, "credentials": plaintext, **meta_for(row)}


# --------------------------------------------------------- materialisation
def _lock_down(path: Path, *, is_dir: bool) -> None:
    """Restrict ``path`` to the owning process. Best-effort, never fatal.

    ``chmod`` is a no-op on Windows and can fail on exotic filesystems; a
    failure here must not abort a build, because the containing directory is
    already inside the workspace volume. On Linux — which is where the hub
    actually runs — this is what stops the materialised credential from being
    world-readable inside the container.
    """
    try:
        path.chmod(stat.S_IRWXU if is_dir else (stat.S_IRUSR | stat.S_IWUSR))
    except OSError:  # pragma: no cover - platform dependent
        pass


def materialize(row: ClaudeCredentials) -> Path:
    """Write ``row``'s decrypted credential into a locked-down config dir.

    Ported from QAgent's ``materialize()``, which the original hub port
    deliberately left out; ADR 0007 now requires it, because the Claude CLI
    reads its OAuth session from ``<CLAUDE_CONFIG_DIR>/.credentials.json`` and
    has no other way to be handed one.

    The directory is chosen from the **credential row's own owner**, not the
    requesting user, so a member running under the shared credential shares its
    materialised copy instead of minting a second plaintext copy of the same
    secret. Returns the *directory* — that is the value ``CLAUDE_CONFIG_DIR``
    takes. Rewritten on every call, so a re-uploaded credential takes effect on
    the next build without a restart.

    Raises:
        ClaudeCredentialsError: the stored blob does not decrypt under the
            current key. Never writes the ciphertext as if it were the file.
    """
    from app.services.workspace_scope import scoped_claude_config_dir

    plaintext = crypto.decrypt(row.credentials)
    if plaintext is None:
        raise ClaudeCredentialsError(
            "stored Claude credential could not be decrypted with the current key"
        )

    config_dir = scoped_claude_config_dir(row.owner_id)
    config_dir.mkdir(parents=True, exist_ok=True)
    _lock_down(config_dir, is_dir=True)

    creds_path = config_dir / ".credentials.json"
    creds_path.write_text(plaintext, encoding="utf-8")
    _lock_down(creds_path, is_dir=False)
    return config_dir


def resolve_effective_config_dir(
    db: Session, owner_id: int | None
) -> tuple[Path, str] | None:
    """Materialise the credential ``owner_id`` should run with.

    Returns ``(config_dir, source)`` where ``source`` is ``"own"`` or
    ``"shared"`` (so the caller can stamp the usage row with which account paid),
    or ``None`` when there is no credential at all. There is no interactive
    ``claude login`` fallback — a hub with no credential fails the build with a
    message a human can act on.
    """
    row, source = resolve(db, owner_id)
    if row is None:
        return None
    return materialize(row), source


# ------------------------------------------------------------------ writes
def _apply(row: ClaudeCredentials, raw: str, parsed: ParsedCredential) -> None:
    """Write the encrypted blob and its parsed metadata onto ``row``."""
    row.credentials = crypto.encrypt(raw) or ""
    row.status = STATUS_ACTIVE
    row.expires_at = parsed.expires_at
    row.scopes = list(parsed.scopes)
    row.subscription_type = parsed.subscription_type
    # Presence only — the refresh token stays in the encrypted blob above. Set
    # on every write, so a row that has been through this path is never NULL and
    # never needs the lazy backfill.
    row.has_refresh_token = parsed.has_refresh_token


def _upsert(
    db: Session, owner_id: int | None, raw: str, label: str
) -> ClaudeCredentials:
    parsed = parse_credentials(raw)
    row = (
        db.query(ClaudeCredentials).filter(ClaudeCredentials.owner_id == owner_id).first()
        if owner_id is not None
        else get_shared(db)
    )
    if row is None:
        row = ClaudeCredentials(owner_id=owner_id)
        db.add(row)
    _apply(row, raw, parsed)
    row.label = (label or "").strip()[:120]
    if owner_id is None:
        row.prefer_shared = False  # meaningless on the shared row
    db.commit()
    db.refresh(row)
    return row


def upsert_own(db: Session, owner_id: int, raw: str, label: str = "") -> ClaudeCredentials:
    """Store or replace ``owner_id``'s own credential."""
    return _upsert(db, owner_id, raw, label)


def upsert_shared(db: Session, raw: str, label: str = "") -> ClaudeCredentials:
    """Store or replace the workspace's shared credential. Admin-gated at the router."""
    return _upsert(db, None, raw, label)


def set_preferred_mode(db: Session, owner_id: int, mode: str) -> ClaudeCredentials:
    """Record whether ``owner_id`` prefers their own credential or the shared one.

    Non-destructive: the uploaded credential stays on file as ``prefer_shared``
    so the user can flip back without re-uploading. Requires an own credential
    to store the preference on, and ``"shared"`` requires a shared credential to
    fall back to — both 400 otherwise.
    """
    if mode not in (MODE_OWN, MODE_SHARED):
        raise ClaudeCredentialsError('mode must be "own" or "shared"')
    own = get_own(db, owner_id)
    if own is None:
        raise ClaudeCredentialsError("no personal Claude credential on file to switch")
    if mode == MODE_SHARED and get_shared(db) is None:
        raise ClaudeCredentialsError("no shared Claude account is configured")
    own.prefer_shared = mode == MODE_SHARED
    db.commit()
    db.refresh(own)
    return own


def persist_refreshed_from_raw(db: Session, owner_id: int | None, raw: str) -> bool:
    """Capture a token the Claude CLI rotated on an agent host (INTEGRATION.md §4).

    OAuth access tokens live hours; the CLI rewrites ``.credentials.json`` in
    place whenever it refreshes one. The agent's config dir is transient, so
    unless the rotated file is posted back here the stored refresh token goes
    stale and the credential eventually dies.

    Writes to whichever row :func:`resolve` selected, and only when the posted
    file holds a **non-empty** access token with a **strictly newer**
    ``expiresAt`` than the stored one. Those two guards mean a failed or
    logged-out refresh can never clobber a good credential. Returns True when it
    updated.
    """
    if not raw or not raw.strip():
        return False
    row, _source = resolve(db, owner_id)
    if row is None:
        return False
    return _persist_if_newer(db, row, raw)


def _persist_if_newer(db: Session, row: ClaudeCredentials, raw: str) -> bool:
    try:
        parsed = parse_credentials(raw)
    except ClaudeCredentialsError:
        return False  # logged-out / malformed — never persist
    if parsed.expires_at_ms is None:
        return False  # cannot prove it is fresher

    stored = crypto.decrypt(row.credentials) or ""
    old_ms: int | None = None
    if stored:
        try:
            old_ms = parse_credentials(stored).expires_at_ms
        except ClaudeCredentialsError:
            old_ms = None
    if old_ms is not None and parsed.expires_at_ms <= old_ms:
        return False  # not a fresher token

    _apply(row, raw, parsed)
    db.commit()
    return True


def mark_expired(db: Session, row: ClaudeCredentials) -> bool:
    """Flag ``row`` as no longer usable. Idempotent; returns True on a change.

    Deliberately one-way. Clearing the flag happens only when a genuinely newer
    token arrives (:func:`upsert_own` / :func:`persist_refreshed_from_raw`) —
    the hub cannot prove a token works, so nothing here may declare it healthy.
    """
    if row.status == STATUS_EXPIRED:
        return False
    row.status = STATUS_EXPIRED
    db.commit()
    return True


def delete_own(db: Session, owner_id: int) -> bool:
    """Delete ``owner_id``'s own credential (they fall back to shared, if any)."""
    row = get_own(db, owner_id)
    if row is None:
        return False
    db.delete(row)
    db.commit()
    return True


def delete_shared(db: Session) -> bool:
    """Delete the shared credential. Admin-gated at the router."""
    row = get_shared(db)
    if row is None:
        return False
    db.delete(row)
    db.commit()
    return True


# ------------------------------------------------------------------ metadata
def meta_for(row: ClaudeCredentials | None, now: datetime | None = None) -> dict | None:
    """Public metadata for one row — assembled field by field, never the blob.

    ``row.credentials`` is not read here and there is no option to include it;
    that is what makes "only ``/resolve`` returns material" a property of the
    code rather than a convention.
    """
    if row is None:
        return None
    days = days_left(row.expires_at, now)
    return {
        "label": row.label,
        "status": derived_status(row, now),
        "storedStatus": row.status,
        "expiresAt": row.expires_at,
        "daysLeft": days,
        "scopes": list(row.scopes or []),
        "subscriptionType": row.subscription_type,
        "lastRefreshed": row.updated_at,
        "preferShared": bool(row.prefer_shared),
        # The presence of a refresh token, so the SPA can derive the same status
        # the hub just did. Never the token — see the model docstring.
        "hasRefreshToken": bool(row.has_refresh_token),
    }


def _assigned_users(db: Session) -> int:
    """Active users who fall back to the shared credential (have no own row)."""
    from app.models.user import User

    owned_ids = [
        r[0]
        for r in db.query(ClaudeCredentials.owner_id)
        .filter(ClaudeCredentials.owner_id.isnot(None))
        .all()
    ]
    query = db.query(User).filter(User.is_active.is_(True))
    if owned_ids:
        query = query.filter(User.id.notin_(owned_ids))
    return query.count()


def status_for(db: Session, owner_id: int | None, now: datetime | None = None) -> dict:
    """The credential summary for the settings screen. Never leaks the token.

    ``mode`` is what :func:`resolve` would actually pick for this user.
    """
    own_row = get_own(db, owner_id)
    shared_row = get_shared(db)
    # Resolve any NULL refresh-token flag before the status is derived from it,
    # or a pre-existing row reads `expired` once more before it self-heals.
    backfill_refresh_flag(db, own_row)
    backfill_refresh_flag(db, shared_row)
    _row, mode = resolve(db, owner_id)
    shared_meta = meta_for(shared_row, now)
    if shared_meta is not None:
        shared_meta["assignedUsers"] = _assigned_users(db)
    return {
        "hasOwn": own_row is not None,
        "hasShared": shared_row is not None,
        "mode": mode,
        "preferShared": bool(own_row.prefer_shared) if own_row is not None else False,
        "own": meta_for(own_row, now),
        "shared": shared_meta,
    }


# ------------------------------------------------------------------ testing
def _scoped_row(db: Session, owner_id: int | None, scope: str) -> ClaudeCredentials | None:
    if scope == MODE_SHARED:
        return get_shared(db)
    if scope == MODE_OWN:
        return get_own(db, owner_id)
    return resolve(db, owner_id)[0]


def verify(db: Session, owner_id: int | None, scope: str = "effective") -> dict:
    """Check a stored credential without calling Claude.

    The hub does not invoke the CLI (CLAUDE.md › What this repo is), so this is
    a *storage* test, not a liveness test: the credential exists, decrypts under
    the current key, parses, and has not passed its expiry. That is everything
    the hub can honestly assert; only the agent that runs the CLI can report
    real usability, which it does by posting to
    ``PUT /credentials/claude/refreshed`` or by the credential going stale.

    Marks the row expired when its expiry has passed **and there is no refresh
    token** — an elapsed access token with a refresh token beside it is not a
    dead credential, it is one the CLI renews on its next run (issue #63), and
    that reports as ``refreshable`` rather than being flagged. Never marks a
    credential healthy — see :func:`mark_expired`.

    Returns ``{"ok", "result", "message"}`` where ``result`` is one of
    ``no_credential | undecryptable | invalid | expired | refreshable | ok``.
    """
    if scope not in (MODE_OWN, MODE_SHARED, "effective"):
        scope = "effective"
    row = _scoped_row(db, owner_id, scope)
    if row is None:
        return {
            "ok": False,
            "result": "no_credential",
            "message": "No Claude credential is configured.",
        }
    plaintext = crypto.decrypt(row.credentials)
    if plaintext is None:
        return {
            "ok": False,
            "result": "undecryptable",
            "message": "The stored credential cannot be decrypted with the current key.",
        }
    try:
        parsed = parse_credentials(plaintext)
    except ClaudeCredentialsError:
        return {"ok": False, "result": "invalid", "message": INVALID_CREDENTIAL_MESSAGE}
    # The blob has just been decrypted and parsed, so the flag can be settled
    # from the authoritative source rather than left to the lazy backfill.
    if row.has_refresh_token != parsed.has_refresh_token:
        row.has_refresh_token = parsed.has_refresh_token
        db.commit()
    status = derived_status(row)
    if status == STATUS_REFRESHABLE:
        return {
            "ok": True,
            "result": "refreshable",
            "message": (
                "The access token has elapsed, but this credential carries a "
                "refresh token — the Claude CLI renews it on the next run."
            ),
        }
    if status == STATUS_EXPIRED:
        mark_expired(db, row)
        return {
            "ok": False,
            "result": "expired",
            "message": "This Claude credential has expired. Upload a fresh one.",
        }
    return {"ok": True, "result": "ok", "message": "Credential is stored and readable."}
