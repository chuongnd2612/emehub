"""Auth dependencies and cookie helpers.

* :func:`require_user`  — the default for every protected route. Decodes the
  bearer access token **for the hub's own audience**, loads the active user, and
  401s otherwise.
* :func:`require_role` / :func:`require_admin` — role gates on top.
* :func:`require_audience` — factory for routes that must only be reachable by a
  specific agent's token (a ``qagent`` token must not satisfy a ``dagent`` route).
* :func:`current_user`  — the never-raising variant used by ownership scoping.

There is no "auth disabled" branch anywhere in this module, by design
(CLAUDE.md › Never fail open).

Cookies: an HttpOnly refresh cookie plus a readable CSRF cookie for the
double-submit check. ``Secure`` is gated on ``EMEHUB_COOKIE_SECURE`` so
http-localhost development works while an HTTPS deployment stays secure.
"""

from __future__ import annotations

from fastapi import Depends, HTTPException, Request, Response
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.config import AUDIENCE_HUB, settings
from app.db import get_db
from app.models.user import ROLE_ADMIN, User
from app.services import auth_service

REFRESH_COOKIE = "emehub_refresh"
CSRF_COOKIE = "emehub_csrf"
CSRF_HEADER = "X-CSRF-Token"

_bearer = HTTPBearer(auto_error=False)


def unauthorized(detail: str = "Not authenticated") -> HTTPException:
    return HTTPException(status_code=401, detail=detail)


def _resolve(
    credentials: HTTPAuthorizationCredentials | None,
    db: Session,
    audience: str | None,
) -> User:
    """Decode, validate and load. ``audience=None`` accepts any *registered*
    audience — see :func:`require_principal`."""
    if credentials is None or not credentials.credentials:
        raise unauthorized()
    try:
        if audience is None:
            payload = auth_service.decode_any_registered(credentials.credentials)
        else:
            payload = auth_service.decode_access_token(credentials.credentials, audience)
    except auth_service.AuthError as exc:
        raise unauthorized(str(exc)) from exc
    return _load_principal(db, payload)


def _load_principal(db: Session, payload: dict, *, aud: str | None = None) -> User:
    """Load the active user behind a decoded payload and check its session.

    Split out of :func:`_resolve` so a credential grant goes through **exactly**
    the same user and session checks as an access token — in particular the live
    session lookup, which is what makes revoking a hub session kill a grant
    immediately (ADR 0009). ``aud`` overrides the audience stamped on the user for
    a grant, where the meaningful audience is the agent named in ``agt`` rather
    than the internal grant audience.
    """
    try:
        user_id = int(payload.get("sub") or 0)
    except (TypeError, ValueError) as exc:
        raise unauthorized("Invalid token subject") from exc
    user = db.get(User, user_id)
    if user is None or not user.is_active:
        raise unauthorized("User not found or inactive")
    # The session behind the token must still be live — revoking a session must
    # take effect immediately at the hub, not only when the access token expires.
    sid = payload.get("sid") or ""
    if not sid or auth_service.get_valid_session(db, sid) is None:
        raise unauthorized("Session revoked or expired")
    user._sid = sid  # type: ignore[attr-defined]
    user._aud = aud or payload.get("aud")  # type: ignore[attr-defined]
    return user


def require_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: Session = Depends(get_db),
) -> User:
    """The authenticated user, from a bearer token minted for the hub."""
    return _resolve(credentials, db, AUDIENCE_HUB)


def require_principal(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: Session = Depends(get_db),
) -> User:
    """The user behind a token minted for **any registered audience**.

    For the endpoints in the integration contract (``GET /me``,
    ``POST /audit/events``): an agent calls those with the token it holds, whose
    ``aud`` is its own id, not ``emehub``. Everything that manages the hub itself
    uses :func:`require_user` instead, so a ``qagent`` token can read identity
    but cannot, say, create a user. An unregistered audience still fails.
    """
    return _resolve(credentials, db, None)


def require_credential_grant(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: Session = Depends(get_db),
) -> User:
    """The user behind **either** an agent access token **or** a credential grant.

    Wired to exactly three routes — ``GET /credentials/claude/resolve``,
    ``PUT /credentials/claude/refreshed``, ``POST /credentials/claude/usage`` —
    and that wiring is what keeps a grant narrow (ADR 0009). A grant presented
    anywhere else fails, structurally: its audience is never registerable, so
    neither ``decode_access_token`` nor ``decode_any_registered`` will accept it.

    The access-token path is tried first and is unchanged, so everything an agent
    does today keeps working. A grant is then validated just as strictly, plus its
    scope and the agent it names, and goes through the **same** live-session
    lookup — which is what makes revoking the hub session kill a grant on its next
    use, with no grant registry and no revocation list. INTEGRATION.md §2's
    "revoking the session kills every agent" holds for grants verbatim.
    """
    if credentials is None or not credentials.credentials:
        raise unauthorized()
    try:
        return _resolve(credentials, db, None)
    except HTTPException:
        # Not an access token for any registered audience. It may be a grant; if
        # it is neither, the grant decoder's message is the more useful one, since
        # a caller that gets this far is usually an agent whose grant expired.
        pass

    try:
        payload = auth_service.decode_agent_grant(credentials.credentials)
    except auth_service.AuthError as exc:
        raise unauthorized(str(exc)) from exc
    return _load_principal(db, payload, aud=payload.get("agt"))


def require_audience(audience: str):
    """Dependency factory: only a token whose ``aud`` is ``audience`` passes.

    Used where a route belongs to one agent — a ``qagent`` token presented to a
    ``dagent`` route is rejected with 401, per INTEGRATION.md §2 ("an agent that
    accepts a token minted for a different aud is a bug").
    """

    def _dep(
        credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
        db: Session = Depends(get_db),
    ) -> User:
        return _resolve(credentials, db, audience)

    return _dep


def require_role(role: str):
    """Dependency factory: 403 unless the current user holds ``role``."""

    def _dep(user: User = Depends(require_user)) -> User:
        if user.role != role:
            raise HTTPException(status_code=403, detail="Insufficient permissions")
        return user

    return _dep


def require_admin(user: User = Depends(require_user)) -> User:
    """401 when unauthenticated, 403 when authenticated but not an admin."""
    if user.role != ROLE_ADMIN:
        raise HTTPException(status_code=403, detail="Admin privileges required")
    return user


def current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: Session = Depends(get_db),
) -> User | None:
    """Best-effort current user for ownership scoping — **never raises**.

    Returns ``None`` when there is no usable token. ``app.services.ownership``
    treats ``None`` as "sees nothing", so this is not a way around
    :func:`require_user`; it exists so a scoping helper can be called from a
    context where the 401 has already been raised (or never applied).
    """
    if credentials is None or not credentials.credentials:
        return None
    try:
        return _resolve(credentials, db, AUDIENCE_HUB)
    except HTTPException:
        return None


# ---------------------------------------------------------------- cookies
def set_auth_cookies(
    response: Response, *, refresh_token: str, csrf_token: str, remember: bool
) -> None:
    max_age = int(auth_service.refresh_ttl(remember).total_seconds())
    domain = settings.cookie_domain or None
    response.set_cookie(
        REFRESH_COOKIE,
        refresh_token,
        max_age=max_age,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        path=settings.cookie_path,
        domain=domain,
    )
    response.set_cookie(
        CSRF_COOKIE,
        csrf_token,
        max_age=max_age,
        httponly=False,  # readable by the SPA so it can echo it in X-CSRF-Token
        secure=settings.cookie_secure,
        samesite="lax",
        path=settings.cookie_path,
        domain=domain,
    )


def clear_auth_cookies(response: Response) -> None:
    domain = settings.cookie_domain or None
    response.delete_cookie(REFRESH_COOKIE, path=settings.cookie_path, domain=domain)
    response.delete_cookie(CSRF_COOKIE, path=settings.cookie_path, domain=domain)


def read_refresh_cookie(request: Request) -> str | None:
    return request.cookies.get(REFRESH_COOKIE)


def read_csrf_cookie(request: Request) -> str | None:
    return request.cookies.get(CSRF_COOKIE)
