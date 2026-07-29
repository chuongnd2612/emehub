"""Auth router — login, MFA, refresh, profile, 2FA, sessions, admin users.

Public endpoints (login, MFA step, refresh, request-reset, reset) are the only
ones in :data:`app.security.PUBLIC_PATHS`. Every other endpoint here declares
``Depends(require_user)`` or ``Depends(require_admin)`` explicitly — this router
is registered *without* a blanket dependency precisely because it straddles the
boundary, so each route says out loud what it requires.

Login sets an HttpOnly ``emehub_refresh`` cookie plus a readable ``emehub_csrf``
cookie; refresh reads both and validates the double-submit header. The plaintext
refresh token is never returned in a body and never logged.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.orm import Session

from app.config import AUDIENCE_HUB, settings
from app.db import get_db, utcnow
from app.deps_auth import (
    CSRF_HEADER,
    clear_auth_cookies,
    read_csrf_cookie,
    read_refresh_cookie,
    require_admin,
    require_user,
    set_auth_cookies,
)
from app.logging import logger
from app.models.session import Session as AuthSession
from app.models.user import ROLE_ADMIN, USER_ROLES, User
from app.schemas import (
    AdminCreateUserRequest,
    AdminInviteUserRequest,
    AdminInviteUserResponse,
    AdminUpdateUserRequest,
    AdminUserOut,
    ChangePasswordRequest,
    LoginRequest,
    LoginResponse,
    MfaLoginRequest,
    OkResponse,
    RefreshRequest,
    RefreshResponse,
    RequestResetRequest,
    RequestResetResponse,
    ResetRequest,
    SessionOut,
    TotpCodeRequest,
    TotpDisableRequest,
    TotpSetupResponse,
    UpdateMeRequest,
    UserOut,
)
from app.services import audit_service, auth_service

router = APIRouter(tags=["auth"])


# ---------------------------------------------------------------- helpers
def _client_meta(request: Request) -> tuple[str, str]:
    return request.headers.get("user-agent", ""), (
        request.client.host if request.client else ""
    )


def resolve_audiences(requested: list[str] | None) -> list[str]:
    """Validate the requested audiences, or default to every registered one.

    An audience the hub has not been configured for is a 400 and **no token is
    issued at all** — not a partial bundle. INTEGRATION.md §2.
    """
    registered = list(auth_service.registered_audiences())
    if not requested:
        return registered
    unknown = [a for a in requested if a not in registered]
    if unknown:
        raise HTTPException(
            status_code=400,
            detail=f"Unregistered audience(s): {', '.join(sorted(set(unknown)))}",
        )
    # Preserve request order, drop duplicates, always include the hub's own
    # audience so the caller can talk to the hub with what it got back.
    seen: list[str] = []
    for aud in [*requested, AUDIENCE_HUB]:
        if aud not in seen:
            seen.append(aud)
    return seen


def _issue_login(
    db: Session,
    user: User,
    request: Request,
    response: Response,
    *,
    remember: bool,
    audiences: list[str],
) -> LoginResponse:
    ua, ip = _client_meta(request)
    session, refresh_token = auth_service.create_session(
        db, user, remember=remember, user_agent=ua, ip=ip
    )
    user.last_active = utcnow()
    db.add(user)
    db.commit()
    csrf = auth_service.generate_csrf_token()
    set_auth_cookies(
        response, refresh_token=refresh_token, csrf_token=csrf, remember=remember
    )
    tokens = auth_service.create_access_tokens(user, session.id, audiences)
    return LoginResponse(
        access_token=tokens[AUDIENCE_HUB],
        tokens=tokens,
        expires_in=int(auth_service.access_ttl().total_seconds()),
        user=UserOut.model_validate(user),
    )


def _is_prod() -> bool:
    """Prod == secure cookies (HTTPS). Governs whether a reset token is echoed."""
    return settings.cookie_secure


# ---------------------------------------------------------------- public
@router.post("/auth/login", response_model=LoginResponse)
def login(
    body: LoginRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
) -> LoginResponse:
    audiences = resolve_audiences(body.audiences)
    user = auth_service.authenticate(db, body.email, body.password)
    if user is None:
        # One message for both "no such user" and "wrong password".
        raise HTTPException(status_code=401, detail="Invalid email or password")
    if user.totp_enabled:
        return LoginResponse(
            mfa_required=True, mfa_token=auth_service.create_mfa_token(user)
        )
    result = _issue_login(
        db, user, request, response, remember=body.remember, audiences=audiences
    )
    audit_service.record(
        category="auth",
        action="Signed in",
        target=user.email,
        actor=user.email,
        actor_id=user.id,
    )
    return result


@router.post("/auth/login/mfa", response_model=LoginResponse)
def login_mfa(
    body: MfaLoginRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
) -> LoginResponse:
    audiences = resolve_audiences(body.audiences)
    try:
        payload = auth_service.decode_mfa_token(body.mfa_token)
    except auth_service.AuthError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    user = db.get(User, int(payload.get("sub") or 0))
    if user is None or not user.is_active:
        raise HTTPException(status_code=401, detail="User not found or inactive")
    if not (user.totp_enabled and auth_service.verify_totp(user.totp_secret or "", body.code)):
        raise HTTPException(status_code=401, detail="Invalid verification code")
    result = _issue_login(
        db, user, request, response, remember=False, audiences=audiences
    )
    audit_service.record(
        category="auth",
        action="Signed in (2FA)",
        target=user.email,
        actor=user.email,
        actor_id=user.id,
    )
    return result


@router.post("/auth/refresh", response_model=RefreshResponse)
def refresh(
    request: Request,
    response: Response,
    body: RefreshRequest | None = None,
    db: Session = Depends(get_db),
) -> RefreshResponse:
    """Rotate the refresh token and mint **one access token per audience**.

    The only place a token is renewed in the whole suite — agents must not
    issue, refresh or extend tokens (INTEGRATION.md §2).
    """
    audiences = resolve_audiences(body.audiences if body else None)
    token = read_refresh_cookie(request)
    if not token:
        raise HTTPException(status_code=401, detail="Missing refresh token")
    if not auth_service.verify_csrf(read_csrf_cookie(request), request.headers.get(CSRF_HEADER)):
        raise HTTPException(status_code=403, detail="Invalid CSRF token")
    session = auth_service.find_session_by_refresh(db, token)
    if session is None:
        raise HTTPException(status_code=401, detail="Invalid or expired session")
    user = db.get(User, session.user_id)
    if user is None or not user.is_active:
        raise HTTPException(status_code=401, detail="User not found or inactive")
    new_token = auth_service.rotate(db, session)
    user.last_active = utcnow()
    db.add(user)
    db.commit()
    csrf = auth_service.generate_csrf_token()
    remember = (
        (session.expires_at - session.created_at).days >= 1
        if session.expires_at and session.created_at
        else False
    )
    set_auth_cookies(response, refresh_token=new_token, csrf_token=csrf, remember=remember)
    tokens = auth_service.create_access_tokens(user, session.id, audiences)
    return RefreshResponse(
        access_token=tokens[AUDIENCE_HUB],
        tokens=tokens,
        expires_in=int(auth_service.access_ttl().total_seconds()),
        user=UserOut.model_validate(user),
    )


@router.post("/auth/request-reset", response_model=RequestResetResponse)
def request_reset(
    body: RequestResetRequest, db: Session = Depends(get_db)
) -> RequestResetResponse:
    user = auth_service.get_user_by_email(db, body.email)
    if user is None:
        # Same response either way — never leak which emails exist.
        return RequestResetResponse(ok=True, token=None)
    token = auth_service.create_reset_token(user)
    # DEV STUB: email delivery is not wired yet. Outside prod the token is
    # returned so the flow is testable; in prod it is neither returned nor logged.
    if _is_prod():
        logger.info("Password reset requested for %s", user.email)
        return RequestResetResponse(ok=True, token=None)
    return RequestResetResponse(ok=True, token=token)


@router.post("/auth/reset", response_model=OkResponse)
def reset_password(body: ResetRequest, db: Session = Depends(get_db)) -> OkResponse:
    try:
        payload = auth_service.decode_reset_token(body.token)
    except auth_service.AuthError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    user = db.get(User, int(payload.get("sub") or 0))
    if user is None:
        raise HTTPException(status_code=400, detail="Invalid reset token")
    user.password_hash = auth_service.hash_password(body.password)
    db.add(user)
    db.commit()
    # Every existing session dies with the old password.
    auth_service.revoke_all(db, user.id)
    audit_service.record(
        category="auth",
        action="Reset password",
        target=user.email,
        actor=user.email,
        actor_id=user.id,
    )
    return OkResponse()


# ---------------------------------------------------------------- authenticated
@router.get("/auth/me", response_model=UserOut)
def get_me(user: User = Depends(require_user)) -> UserOut:
    return UserOut.model_validate(user)


@router.patch("/auth/me", response_model=UserOut)
def update_me(
    body: UpdateMeRequest,
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
) -> UserOut:
    if body.first_name is not None:
        user.first_name = body.first_name
    if body.last_name is not None:
        user.last_name = body.last_name
    db.add(user)
    db.commit()
    db.refresh(user)
    return UserOut.model_validate(user)


@router.delete("/auth/me", response_model=OkResponse)
def delete_me(
    response: Response,
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
) -> OkResponse:
    """Delete your own account. The last active admin cannot delete themselves —
    the same lockout guard the admin endpoints apply."""
    if user.role == ROLE_ADMIN and user.is_active and _active_admin_count(db, exclude_id=user.id) == 0:
        raise HTTPException(status_code=400, detail="Cannot remove the last active admin")
    db.query(AuthSession).filter(AuthSession.user_id == user.id).delete(
        synchronize_session=False
    )
    email = user.email
    db.delete(user)
    db.commit()
    clear_auth_cookies(response)
    audit_service.record(category="auth", action="Deleted account", target=email, actor=email)
    return OkResponse()


@router.post("/auth/change-password", response_model=OkResponse)
def change_password(
    body: ChangePasswordRequest,
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
) -> OkResponse:
    if not auth_service.verify_password(user.password_hash, body.current_password):
        raise HTTPException(status_code=400, detail="Current password is incorrect")
    user.password_hash = auth_service.hash_password(body.new_password)
    db.add(user)
    db.commit()
    # Keep this session, kill the others — a password change should log out the
    # devices the user is worried about.
    auth_service.revoke_all(db, user.id, keep_sid=getattr(user, "_sid", "") or "")
    audit_service.record(category="auth", action="Changed password", target=user.email)
    return OkResponse()


@router.post("/auth/logout", response_model=OkResponse)
def logout(
    response: Response,
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
) -> OkResponse:
    sid = getattr(user, "_sid", None)
    if sid:
        auth_service.revoke(db, sid)
    clear_auth_cookies(response)
    audit_service.record(category="auth", action="Signed out", target=user.email)
    return OkResponse()


# ---------------------------------------------------------------- 2FA
@router.post("/auth/2fa/setup", response_model=TotpSetupResponse)
def totp_setup(
    user: User = Depends(require_user), db: Session = Depends(get_db)
) -> TotpSetupResponse:
    """Generate an enrolment secret. Not enabled until a code is verified — the
    only response in the API that contains the TOTP secret."""
    secret = auth_service.generate_totp_secret()
    user.totp_secret = secret
    user.totp_enabled = False
    db.add(user)
    db.commit()
    return TotpSetupResponse(
        secret=secret, otpauth_uri=auth_service.totp_provisioning_uri(secret, user.email)
    )


@router.post("/auth/2fa/enable", response_model=OkResponse)
def totp_enable(
    body: TotpCodeRequest,
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
) -> OkResponse:
    if not user.totp_secret:
        raise HTTPException(status_code=400, detail="Run 2FA setup first")
    if not auth_service.verify_totp(user.totp_secret, body.code):
        raise HTTPException(status_code=400, detail="Invalid verification code")
    user.totp_enabled = True
    db.add(user)
    db.commit()
    audit_service.record(category="auth", action="Enabled 2FA", target=user.email)
    return OkResponse()


@router.post("/auth/2fa/disable", response_model=OkResponse)
def totp_disable(
    body: TotpDisableRequest,
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
) -> OkResponse:
    ok = False
    if body.code and user.totp_secret:
        ok = auth_service.verify_totp(user.totp_secret, body.code)
    if not ok and body.password:
        ok = auth_service.verify_password(user.password_hash, body.password)
    if not ok:
        raise HTTPException(
            status_code=400, detail="Provide a valid 2FA code or your password"
        )
    user.totp_enabled = False
    user.totp_secret = None
    db.add(user)
    db.commit()
    audit_service.record(category="auth", action="Disabled 2FA", target=user.email)
    return OkResponse()


# ---------------------------------------------------------------- sessions
@router.get("/auth/sessions", response_model=list[SessionOut])
def list_sessions(
    user: User = Depends(require_user), db: Session = Depends(get_db)
) -> list[SessionOut]:
    current_sid = getattr(user, "_sid", None)
    out: list[SessionOut] = []
    for s in auth_service.list_sessions(db, user.id):
        item = SessionOut.model_validate(s)
        item.current = s.id == current_sid
        out.append(item)
    return out


@router.delete("/auth/sessions/{session_id}", response_model=OkResponse)
def revoke_session(
    session_id: str, user: User = Depends(require_user), db: Session = Depends(get_db)
) -> OkResponse:
    session = db.get(AuthSession, session_id)
    if session is None or session.user_id != user.id:
        raise HTTPException(status_code=404, detail="Session not found")
    auth_service.revoke(db, session_id)
    audit_service.record(category="auth", action="Revoked session", target=session_id)
    return OkResponse()


@router.post("/auth/sessions/revoke-others", response_model=OkResponse)
def revoke_other_sessions(
    user: User = Depends(require_user), db: Session = Depends(get_db)
) -> OkResponse:
    auth_service.revoke_all(db, user.id, keep_sid=getattr(user, "_sid", "") or "")
    audit_service.record(category="auth", action="Revoked other sessions", target=user.email)
    return OkResponse()


# ---------------------------------------------------------------- admin
def _active_admin_count(db: Session, *, exclude_id: int | None = None) -> int:
    """Active admins, optionally excluding one id — the lockout guard's input."""
    query = db.query(User).filter(User.role == ROLE_ADMIN, User.is_active.is_(True))
    if exclude_id is not None:
        query = query.filter(User.id != exclude_id)
    return query.count()


@router.get("/auth/users", response_model=list[AdminUserOut])
def list_users(
    _: User = Depends(require_admin), db: Session = Depends(get_db)
) -> list[AdminUserOut]:
    rows = db.query(User).order_by(User.created_at.asc(), User.id.asc()).all()
    out: list[AdminUserOut] = []
    for u in rows:
        item = AdminUserOut.model_validate(u)
        item.session_count = len(auth_service.list_sessions(db, u.id))
        out.append(item)
    return out


@router.post("/auth/users", response_model=UserOut, status_code=201)
def create_user(
    body: AdminCreateUserRequest,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> UserOut:
    email = auth_service.normalize_email(body.email)
    if not email:
        raise HTTPException(status_code=400, detail="Email is required")
    if body.role not in USER_ROLES:
        raise HTTPException(status_code=400, detail=f"Invalid role '{body.role}'")
    if not body.password:
        raise HTTPException(status_code=400, detail="Password is required")
    if auth_service.get_user_by_email(db, email) is not None:
        raise HTTPException(status_code=409, detail="A user with that email already exists")
    user = User(
        email=email,
        first_name=body.first_name,
        last_name=body.last_name,
        role=body.role,
        password_hash=auth_service.hash_password(body.password),
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    audit_service.record(
        category="identity", action="Created user", target=email, meta=f"role={body.role}"
    )
    return UserOut.model_validate(user)


@router.post("/auth/users/invite", response_model=AdminInviteUserResponse, status_code=201)
def invite_user(
    body: AdminInviteUserRequest,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> AdminInviteUserResponse:
    """Create an account with no usable password and hand back a reset token so
    the invitee sets one through ``/auth/reset``."""
    email = auth_service.normalize_email(body.email)
    if not email:
        raise HTTPException(status_code=400, detail="Email is required")
    if body.role not in USER_ROLES:
        raise HTTPException(status_code=400, detail=f"Invalid role '{body.role}'")
    if auth_service.get_user_by_email(db, email) is not None:
        raise HTTPException(status_code=409, detail="A user with that email already exists")
    user = User(
        email=email,
        first_name=body.first_name,
        last_name=body.last_name,
        role=body.role,
        password_hash="",  # unusable until the invite is redeemed
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    token = auth_service.create_reset_token(user)
    audit_service.record(
        category="identity", action="Invited user", target=email, meta=f"role={body.role}"
    )
    return AdminInviteUserResponse(
        user=UserOut.model_validate(user),
        reset_token=None if _is_prod() else token,
    )


@router.patch("/auth/users/{user_id}", response_model=UserOut)
def update_user(
    user_id: int,
    body: AdminUpdateUserRequest,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> UserOut:
    target = db.get(User, user_id)
    if target is None:
        raise HTTPException(status_code=404, detail="User not found")
    if body.role is not None and body.role not in USER_ROLES:
        raise HTTPException(status_code=400, detail=f"Invalid role '{body.role}'")
    new_role = body.role if body.role is not None else target.role
    new_is_active = body.is_active if body.is_active is not None else target.is_active
    # Lockout guard: never leave the workspace with zero active admins — covers
    # an admin demoting or deactivating themselves as well as someone else.
    was_active_admin = target.role == ROLE_ADMIN and target.is_active
    will_be_active_admin = new_role == ROLE_ADMIN and new_is_active
    if (
        was_active_admin
        and not will_be_active_admin
        and _active_admin_count(db, exclude_id=target.id) == 0
    ):
        raise HTTPException(
            status_code=400, detail="Cannot leave the workspace with zero active admins"
        )
    if body.first_name is not None:
        target.first_name = body.first_name
    if body.last_name is not None:
        target.last_name = body.last_name
    target.role = new_role
    target.is_active = new_is_active
    db.add(target)
    db.commit()
    db.refresh(target)
    if not new_is_active:
        # A deactivated account must lose its live sessions immediately.
        auth_service.revoke_all(db, target.id)
    audit_service.record(category="identity", action="Updated user", target=target.email)
    return UserOut.model_validate(target)


@router.delete("/auth/users/{user_id}", response_model=OkResponse)
def delete_user(
    user_id: int, _: User = Depends(require_admin), db: Session = Depends(get_db)
) -> OkResponse:
    target = db.get(User, user_id)
    if target is None:
        raise HTTPException(status_code=404, detail="User not found")
    if (
        target.role == ROLE_ADMIN
        and target.is_active
        and _active_admin_count(db, exclude_id=target.id) == 0
    ):
        raise HTTPException(status_code=400, detail="Cannot remove the last active admin")
    db.query(AuthSession).filter(AuthSession.user_id == target.id).delete(
        synchronize_session=False
    )
    email = target.email
    db.delete(target)
    db.commit()
    audit_service.record(category="identity", action="Deleted user", target=email)
    return OkResponse()
