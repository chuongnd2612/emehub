"""Auth service — password hashing, audience-scoped JWTs, refresh sessions,
TOTP and CSRF.

Signing uses ``EMEHUB_JWT_SECRET`` and only that. It is never used to derive an
encryption key (that is ``app.crypto`` with ``EMEHUB_ENCRYPTION_KEY``; ADR 0005).

## Access tokens — INTEGRATION.md §2

Every access token carries **exactly** this claim set, no more:

    {sub, email, role, sid, aud, iss, iat, exp}

with a ``kid`` JOSE header. The header is present from the very first token even
though Phase 1 signs HS256 with a shared secret, so the Phase-3 move to RS256 +
``/.well-known/jwks.json`` adds a key, not a breaking change
(INTEGRATION.md › Key distribution).

``aud`` is minted per audience and verified on decode. A token for ``qagent``
cannot be replayed against ``dagent`` or against the hub's own API, and an
audience the operator has not registered (``EMEHUB_AGENT_*_URL`` unset) is
refused outright — :class:`UnregisteredAudience`.

## Other token kinds

The MFA and reset tokens deliberately live in their own audience namespace
(``emehub:mfa`` / ``emehub:reset``) rather than an extra ``typ`` claim on the
access token, which would break the "exactly this claim set" contract. Since
those audiences can never be registered, a mid-login MFA token can never be
presented as an access token.

## Refresh tokens

Opaque ``secrets.token_urlsafe`` values. Only their sha256 is persisted; the
plaintext lives solely in the HttpOnly refresh cookie and is never logged.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

import jwt
import pyotp
from argon2 import PasswordHasher
from argon2.exceptions import Argon2Error
from sqlalchemy.orm import Session as DbSession

from app.config import AUDIENCE_HUB, settings
from app.db import utcnow
from app.models.session import Session as AuthSession
from app.models.user import User

ISSUER = "emehub"
ALGORITHM = "HS256"

# Key id, present from token #1 so Phase 3 can publish a JWKS and rotate keys
# without agents changing how they read a token. Not derived from the secret —
# a key id is public metadata and must never carry information about the key.
ACCESS_TOKEN_KID = "emehub-hs256-2026-07"

# Internal audiences. Never registerable, so a token minted for one of these can
# never satisfy `decode_access_token`.
AUDIENCE_MFA = f"{AUDIENCE_HUB}:mfa"
AUDIENCE_RESET = f"{AUDIENCE_HUB}:reset"
#: Run-scoped credential grants (ADR 0009). Put in the same never-registerable
#: namespace deliberately: a grant outlives an access token, so it must be
#: *structurally* incapable of satisfying ``decode_access_token`` or
#: ``decode_any_registered``, not merely refused by convention somewhere.
AUDIENCE_GRANT = f"{AUDIENCE_HUB}:grant"

#: The only thing a grant may authorise. A claim rather than an implication of the
#: audience, so a second scope can be added later without making every existing
#: grant ambiguous.
SCOPE_CLAUDE_CREDENTIAL = "claude-credential"

REFRESH_TTL_REMEMBER_DAYS_DEFAULT = 30
REFRESH_TTL_DEFAULT = timedelta(hours=12)

_ph = PasswordHasher()


class AuthError(Exception):
    """Invalid, expired, or wrong-audience token."""


class UnregisteredAudience(AuthError):
    """An audience the hub has not been configured to mint tokens for."""


# ---------------------------------------------------------------- TTLs
def access_ttl() -> timedelta:
    return timedelta(minutes=settings.access_token_ttl_minutes)


def _mfa_ttl() -> timedelta:
    return timedelta(minutes=settings.mfa_token_ttl_minutes)


def _reset_ttl() -> timedelta:
    return timedelta(minutes=settings.reset_token_ttl_minutes)


def refresh_ttl(remember: bool) -> timedelta:
    if remember:
        return timedelta(days=settings.refresh_token_ttl_days)
    return REFRESH_TTL_DEFAULT


# ---------------------------------------------------------------- passwords
def hash_password(password: str) -> str:
    return _ph.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    """Constant-ish time password check. An empty hash (an invited user who has
    not set a password yet) never verifies."""
    if not password_hash or not password:
        return False
    try:
        return _ph.verify(password_hash, password)
    except (Argon2Error, ValueError, TypeError):
        return False


# ---------------------------------------------------------------- audiences
def registered_audiences() -> tuple[str, ...]:
    return settings.registered_audiences


def require_registered_audience(audience: str) -> str:
    """Return ``audience`` if the hub may mint tokens for it, else raise.

    This is the single choke point behind every token-issuing path — "an
    audience not registered must not receive a token".
    """
    if audience not in registered_audiences():
        raise UnregisteredAudience(f"Unknown audience '{audience}'")
    return audience


# ---------------------------------------------------------------- JWTs
def _encode(claims: dict[str, Any], ttl: timedelta) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        **claims,
        "iss": ISSUER,
        "iat": int(now.timestamp()),
        "exp": int((now + ttl).timestamp()),
    }
    return jwt.encode(
        payload,
        settings.jwt_secret,
        algorithm=ALGORITHM,
        headers={"kid": ACCESS_TOKEN_KID},
    )


def _decode(token: str, audience: str | list[str]) -> dict[str, Any]:
    try:
        return jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[ALGORITHM],
            # PyJWT accepts a list here and passes when `aud` matches any entry.
            audience=audience,
            issuer=ISSUER,
            options={"require": ["exp", "iat", "iss", "aud", "sub"]},
        )
    except jwt.ExpiredSignatureError as exc:
        raise AuthError("Token expired") from exc
    except jwt.InvalidAudienceError as exc:
        raise AuthError("Token is not valid for this audience") from exc
    except jwt.InvalidTokenError as exc:
        raise AuthError("Invalid token") from exc


def create_access_token(user: User, sid: str, audience: str = AUDIENCE_HUB) -> str:
    """Mint an access token for one audience.

    Raises :class:`UnregisteredAudience` when ``audience`` is not configured.
    """
    require_registered_audience(audience)
    return _encode(
        {
            "sub": str(user.id),
            "email": user.email,
            "role": user.role,
            "sid": sid,
            "aud": audience,
        },
        access_ttl(),
    )


def create_access_tokens(user: User, sid: str, audiences: list[str]) -> dict[str, str]:
    """Mint one access token per requested audience, in one pass.

    Every audience is validated *before* any token is produced, so a request
    naming one bad audience gets no tokens at all rather than a partial set.
    """
    for audience in audiences:
        require_registered_audience(audience)
    return {aud: create_access_token(user, sid, aud) for aud in audiences}


def decode_access_token(token: str, audience: str = AUDIENCE_HUB) -> dict[str, Any]:
    """Decode and fully validate an access token for ``audience``.

    Verifies signature, ``iss``, ``exp`` and — crucially — that ``aud`` matches.
    The default is the hub's own audience, so a ``qagent`` token presented to a
    hub management endpoint is rejected.
    """
    return _decode(token, audience)


def decode_any_registered(token: str) -> dict[str, Any]:
    """Decode a token minted for **any** registered audience.

    Used by two callers only:

    * the guard middleware, which asks "is this a token this hub issued?" and
      leaves "for whom?" to the route's own dependency; and
    * the agent-facing contract endpoints (``GET /me``, ``POST /audit/events``),
      which an agent calls with the token it holds — its own audience, not the
      hub's.

    An unregistered audience still fails: the audience list is the allowlist.
    """
    return _decode(token, list(registered_audiences()))


# ------------------------------------------------------- run-scoped grants
def grant_ttl() -> timedelta:
    """How long a credential grant lives. See ``Settings.agent_grant_ttl_minutes``."""
    return timedelta(minutes=settings.agent_grant_ttl_minutes)


def create_agent_grant(user: User, sid: str, *, agent_audience: str, run_id: str) -> str:
    """Mint a run-scoped credential grant for ``agent_audience`` (ADR 0009).

    The grant exists because an agent's background run outlives a 15-minute
    access token and may not refresh one: ``/auth/agent-token`` mints from the
    *browser's* refresh cookie, which a daemon thread does not have.

    Three things make it narrow rather than "a long-lived token":

    * ``aud`` is :data:`AUDIENCE_GRANT`, which is never registerable, so this can
      never be accepted as an access token anywhere;
    * ``scp`` names the one thing it may do, and the dependency that accepts it is
      wired to exactly three credential routes;
    * ``sid`` is the *same hub session*, so revoking that session kills the grant
      immediately — ``deps_auth`` re-checks the session row on every request, so
      no grant registry or revocation list is needed.

    Raises :class:`UnregisteredAudience` when ``agent_audience`` is not an agent
    the hub is configured for. The hub's own audience is refused by the caller:
    a grant is for a background agent run, and the hub SPA has a session.
    """
    require_registered_audience(agent_audience)
    return _encode(
        {
            "sub": str(user.id),
            "email": user.email,
            "sid": sid,
            "aud": AUDIENCE_GRANT,
            "agt": agent_audience,
            "scp": SCOPE_CLAUDE_CREDENTIAL,
            "run": run_id,
        },
        grant_ttl(),
    )


def decode_agent_grant(token: str) -> dict[str, Any]:
    """Decode and fully validate a credential grant.

    Requires ``agt`` and ``scp`` in addition to the usual claims, and checks the
    scope, so a token in the grant audience that is missing either is rejected
    rather than treated as unscoped. ``agt`` is validated against the registered
    audiences too: de-registering an agent stops its grants working.
    """
    payload = _decode(token, AUDIENCE_GRANT)
    if payload.get("scp") != SCOPE_CLAUDE_CREDENTIAL:
        raise AuthError("Grant is not valid for this scope")
    agent = payload.get("agt") or ""
    if agent not in registered_audiences():
        raise AuthError(f"Grant names an unregistered agent: '{agent}'")
    return payload


def agent_grant_valid(token: str | None) -> bool:
    """True when ``token`` is a live, in-scope credential grant.

    For the guard middleware only. It answers "did this hub issue this?", and the
    per-route dependency decides what it may reach — which is what confines a
    grant to the three credential routes.
    """
    if not token:
        return False
    try:
        decode_agent_grant(token)
    except AuthError:
        return False
    return True


def access_token_valid(token: str | None, audience: str | None = None) -> bool:
    """True when ``token`` is a live token for ``audience`` (default: any
    registered audience).

    A credential grant is **not** an access token and returns ``False`` here —
    see :func:`agent_grant_valid`."""
    if not token:
        return False
    try:
        if audience is None:
            decode_any_registered(token)
        else:
            decode_access_token(token, audience)
        return True
    except AuthError:
        return False


def create_mfa_token(user: User) -> str:
    return _encode({"sub": str(user.id), "aud": AUDIENCE_MFA}, _mfa_ttl())


def decode_mfa_token(token: str) -> dict[str, Any]:
    return _decode(token, AUDIENCE_MFA)


def create_reset_token(user: User) -> str:
    return _encode({"sub": str(user.id), "aud": AUDIENCE_RESET}, _reset_ttl())


def decode_reset_token(token: str) -> dict[str, Any]:
    return _decode(token, AUDIENCE_RESET)


# ---------------------------------------------------------------- refresh sessions
def hash_refresh(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def create_session(
    db: DbSession, user: User, *, remember: bool = False, user_agent: str = "", ip: str = ""
) -> tuple[AuthSession, str]:
    """Create a refresh session. Returns ``(session, plaintext_refresh_token)``.

    The plaintext is returned once, to be written into the HttpOnly cookie. Only
    its hash reaches the database.
    """
    sid = uuid.uuid4().hex
    token = secrets.token_urlsafe(48)
    now = utcnow()
    session = AuthSession(
        id=sid,
        user_id=user.id,
        refresh_token_hash=hash_refresh(token),
        user_agent=(user_agent or "")[:400],
        ip=(ip or "")[:64],
        created_at=now,
        last_seen_at=now,
        expires_at=now + refresh_ttl(remember),
        revoked_at=None,
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    return session, token


def _as_utc(value: datetime | None) -> datetime | None:
    if value is not None and value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def get_valid_session(db: DbSession, sid: str) -> AuthSession | None:
    """The session, if it exists, is not revoked and has not expired."""
    session = db.get(AuthSession, sid)
    return session if session is not None and is_live(session) else None


def is_live(session: AuthSession) -> bool:
    if session.revoked_at is not None:
        return False
    exp = _as_utc(session.expires_at)
    return exp is None or exp > utcnow()


def verify_refresh(session: AuthSession, token: str) -> bool:
    return hmac.compare_digest(session.refresh_token_hash, hash_refresh(token))


def find_session_by_refresh(db: DbSession, token: str) -> AuthSession | None:
    """Resolve a plaintext refresh token to its live session.

    The hash is deterministic, so this is an indexed-equality lookup rather than
    QAgent's scan-and-compare over every non-revoked row.
    """
    if not token:
        return None
    session = (
        db.query(AuthSession)
        .filter(AuthSession.refresh_token_hash == hash_refresh(token))
        .first()
    )
    if session is None or not is_live(session):
        return None
    # Re-check in constant time; the query above already matched, this guards
    # against a future non-exact lookup being introduced here.
    return session if verify_refresh(session, token) else None


def rotate(db: DbSession, session: AuthSession, *, remember: bool | None = None) -> str:
    """Issue a new refresh token for an existing session. Returns the plaintext."""
    token = secrets.token_urlsafe(48)
    now = utcnow()
    session.refresh_token_hash = hash_refresh(token)
    session.last_seen_at = now
    if remember is not None:
        session.expires_at = now + refresh_ttl(remember)
    db.add(session)
    db.commit()
    db.refresh(session)
    return token


def revoke(db: DbSession, sid: str) -> None:
    session = db.get(AuthSession, sid)
    if session is not None and session.revoked_at is None:
        session.revoked_at = utcnow()
        db.add(session)
        db.commit()


def revoke_all(db: DbSession, user_id: int, keep_sid: str = "") -> int:
    """Revoke every active session for a user except ``keep_sid``. Returns count."""
    rows = (
        db.query(AuthSession)
        .filter(
            AuthSession.user_id == user_id,
            AuthSession.id != keep_sid,
            AuthSession.revoked_at.is_(None),
        )
        .all()
    )
    now = utcnow()
    for row in rows:
        row.revoked_at = now
        db.add(row)
    db.commit()
    return len(rows)


def list_sessions(db: DbSession, user_id: int) -> list[AuthSession]:
    """Live sessions for a user, most recently seen first."""
    rows = (
        db.query(AuthSession)
        .filter(AuthSession.user_id == user_id, AuthSession.revoked_at.is_(None))
        .order_by(AuthSession.last_seen_at.desc())
        .all()
    )
    return [r for r in rows if is_live(r)]


# ---------------------------------------------------------------- TOTP
def generate_totp_secret() -> str:
    return pyotp.random_base32()


def totp_provisioning_uri(secret: str, email: str) -> str:
    return pyotp.TOTP(secret).provisioning_uri(name=email, issuer_name="EmeHub")


def verify_totp(secret: str, code: str) -> bool:
    if not secret or not code:
        return False
    try:
        return pyotp.TOTP(secret).verify(code.strip(), valid_window=1)
    except Exception:  # noqa: BLE001 - a malformed secret must not 500 a login
        return False


# ---------------------------------------------------------------- CSRF
def generate_csrf_token() -> str:
    return secrets.token_urlsafe(32)


def verify_csrf(cookie_value: str | None, header_value: str | None) -> bool:
    """Double-submit check: the readable cookie must equal the request header."""
    if not cookie_value or not header_value:
        return False
    return hmac.compare_digest(cookie_value, header_value)


# ---------------------------------------------------------------- users
def normalize_email(email: str) -> str:
    return (email or "").strip().lower()


def get_user_by_email(db: DbSession, email: str) -> User | None:
    return db.query(User).filter(User.email == normalize_email(email)).first()


def authenticate(db: DbSession, email: str, password: str) -> User | None:
    """The active user when the credentials verify, else ``None``.

    Callers must not distinguish "no such user" from "wrong password" in the
    response — see the single 401 in ``routers/auth.login``.
    """
    user = get_user_by_email(db, email)
    if user is None or not user.is_active:
        return None
    if not verify_password(user.password_hash, password):
        return None
    return user
