"""Pydantic v2 schemas — the HTTP wire contract.

Field names are camelCase on the wire (via ``to_camel``) to match the TypeScript
client in ``app/src/data/``, while staying snake_case in Python.

No schema in this file has a field that could carry a secret: there is no
``password_hash``, no ``totp_secret`` (except the one-shot setup response the
user must see to enrol), no refresh token and no PAT.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel


class ApiModel(BaseModel):
    """Base: populate from ORM attrs, serialize camelCase, accept either casing."""

    model_config = ConfigDict(
        from_attributes=True,
        alias_generator=to_camel,
        populate_by_name=True,
    )


# ---------------------------------------------------------------- users
class UserOut(ApiModel):
    """Public shape of an account. Never carries password_hash or totp_secret."""

    id: int
    email: str
    first_name: str = ""
    last_name: str = ""
    role: str = "member"
    is_active: bool = True
    totp_enabled: bool = False
    created_at: datetime | None = None
    updated_at: datetime | None = None
    last_active: datetime | None = None


class MeOut(ApiModel):
    """``GET /me`` — the shape agents consume (INTEGRATION.md §3)."""

    id: int
    email: str
    name: str = ""
    first_name: str = ""
    last_name: str = ""
    role: str = "member"


class AdminUserOut(UserOut):
    """``UserOut`` plus admin-only fields for the workspace user list."""

    session_count: int = 0


# ---------------------------------------------------------------- login
class LoginRequest(ApiModel):
    email: str
    password: str
    remember: bool = False
    #: Audiences to mint tokens for. Empty means every registered audience.
    audiences: list[str] = Field(default_factory=list)


class TokenBundle(ApiModel):
    """One access token per audience, keyed by audience id.

    Always contains ``emehub``; contains ``qagent`` / ``dagent`` only when the
    operator has registered them (``EMEHUB_AGENT_*_URL``).
    """

    access_token: str
    tokens: dict[str, str] = Field(default_factory=dict)
    expires_in: int = 900


class LoginResponse(ApiModel):
    """Successful login, or an MFA challenge when TOTP is enabled.

    Success: ``{accessToken, tokens, user}``. MFA required:
    ``{mfaRequired: true, mfaToken}`` and nothing else.
    """

    access_token: str | None = None
    tokens: dict[str, str] = Field(default_factory=dict)
    expires_in: int = 900
    user: UserOut | None = None
    mfa_required: bool = False
    mfa_token: str | None = None


class MfaLoginRequest(ApiModel):
    mfa_token: str
    code: str
    audiences: list[str] = Field(default_factory=list)


class RefreshRequest(ApiModel):
    """Optional body for ``POST /auth/refresh``.

    ``audiences`` names which agents to mint tokens for; omitted means all
    registered ones. An unregistered audience is a 400 — no token is issued.
    """

    audiences: list[str] = Field(default_factory=list)


class RefreshResponse(ApiModel):
    access_token: str
    tokens: dict[str, str] = Field(default_factory=dict)
    expires_in: int = 900
    user: UserOut


class AgentTokenRequest(ApiModel):
    """Body for ``POST /auth/agent-token``.

    Exactly one agent audience. The hub's own audience is refused — the hub SPA
    uses ``/auth/refresh``; this endpoint exists for agents (ADR 0008).
    """

    audience: str


class AgentTokenResponse(ApiModel):
    """One agent-audience access token. Carries no refresh material."""

    access_token: str
    audience: str
    expires_in: int = 900
    user: UserOut


class RequestResetRequest(ApiModel):
    email: str


class RequestResetResponse(ApiModel):
    """Email delivery is a dev stub — ``token`` is populated only outside prod."""

    ok: bool = True
    token: str | None = None


class ResetRequest(ApiModel):
    token: str
    password: str


# ---------------------------------------------------------------- profile
class UpdateMeRequest(ApiModel):
    first_name: str | None = None
    last_name: str | None = None


class ChangePasswordRequest(ApiModel):
    current_password: str
    new_password: str


# ---------------------------------------------------------------- 2FA
class TotpSetupResponse(ApiModel):
    secret: str
    otpauth_uri: str


class TotpCodeRequest(ApiModel):
    code: str


class TotpDisableRequest(ApiModel):
    code: str | None = None
    password: str | None = None


# ---------------------------------------------------------------- sessions
class SessionOut(ApiModel):
    id: str
    user_agent: str = ""
    ip: str = ""
    created_at: datetime | None = None
    last_seen_at: datetime | None = None
    expires_at: datetime | None = None
    current: bool = False


# ---------------------------------------------------------------- admin
class AdminCreateUserRequest(ApiModel):
    email: str
    first_name: str = ""
    last_name: str = ""
    role: str = "member"
    password: str


class AdminUpdateUserRequest(ApiModel):
    first_name: str | None = None
    last_name: str | None = None
    role: str | None = None
    is_active: bool | None = None


class AdminInviteUserRequest(ApiModel):
    """Invite a teammate — no password; they set one via ``/auth/reset``."""

    email: str
    first_name: str = ""
    last_name: str = ""
    role: str = "member"


class AdminInviteUserResponse(ApiModel):
    user: UserOut
    reset_token: str | None = None


# ---------------------------------------------------------------- audit
class AuditEventIn(ApiModel):
    """``POST /audit/events`` — an event appended by the hub UI or an agent.

    ``source`` is **not** accepted from the body: it comes from the caller's
    token audience, so an agent cannot append an event attributed to the hub.
    """

    category: str = "agent"
    action: str
    actor_type: str = "user"
    target: str = ""
    status: str = "success"
    meta: str = ""
    detail: dict | None = None


class AuditEventOut(ApiModel):
    id: int
    ts: datetime
    category: str
    source: str
    actor: str
    actor_type: str
    actor_id: int | None = None
    action: str
    target: str
    ip: str
    status: str
    meta: str
    detail: dict | None = None


# ---------------------------------------------------------------- misc
class OkResponse(ApiModel):
    ok: bool = True


class HealthResponse(ApiModel):
    status: str = "ok"
    service: str = "emehub-api"
    version: str = "0.1.0"
