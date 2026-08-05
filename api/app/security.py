"""Auth enforcement — two independent layers, both default-deny.

**Layer 1 — per-route dependencies (primary).** Every router except the two
public ones is registered with ``dependencies=[Depends(require_user)]`` in
``main.create_app``. Protection is therefore a property of *registration*, not of
a string comparison: a new endpoint added to an existing router is protected the
moment it exists, and a route can tighten further (``require_admin``,
``require_audience``) without touching a central list. This is the improvement
over QAgent's arrangement, where authentication lived only in a path allowlist
and a new public-looking prefix was one typo away from being open.

**Layer 2 — the guard middleware (backstop).** Rejects any request whose path is
not in :data:`PUBLIC_PATHS` and does not carry a valid hub access token. It
catches whatever layer 1 misses: a router registered without the dependency, a
mount, a static file, an endpoint declared outside a router.

Neither layer has an off switch. There is no ``EMEHUB_AUTH_REQUIRED``, no
``authDisabled()``, no environment in which either layer becomes a passthrough —
that is the exact bug being removed from DAgent (INTEGRATION.md §6.1) and the
non-negotiable rule in CLAUDE.md. If authentication cannot be performed, the
request is refused.

The allowlist is matched **exactly**, never by prefix: a prefix match on
``/auth`` would expose every future ``/auth/*`` endpoint, and a prefix match is
what path-traversal tricks aim at.
"""

from __future__ import annotations

from starlette.responses import JSONResponse

from app.services import auth_service

#: Paths reachable without an access token. Every one of them is a step in
#: *obtaining* a token, a liveness probe, or generated API documentation.
PUBLIC_PATHS: frozenset[str] = frozenset(
    {
        "/health",
        # Getting a token.
        "/auth/login",
        "/auth/login/mfa",
        "/auth/refresh",
        "/auth/request-reset",
        "/auth/reset",
        # Cross-app hand-off (ADR 0008). NOT unauthenticated: it authenticates
        # with the HttpOnly refresh cookie plus the CSRF double-submit, exactly
        # like /auth/refresh above. It is listed here for the same reason —
        # the guard checks for a *bearer* token, which this caller has not got
        # yet, because getting one is the point of the call.
        "/auth/agent-token",
        # Generated documentation.
        "/openapi.json",
        "/docs",
        "/docs/oauth2-redirect",
        "/redoc",
    }
)


def normalize_path(path: str) -> str:
    """Collapse a request path to the form the allowlist is written in.

    Starlette has already resolved ``.`` / ``..`` segments and percent-encoding
    by this point; this only strips a trailing slash so ``/health/`` and
    ``/health`` are the same entry, and never *adds* anything to the allowlist.
    """
    if len(path) > 1 and path.endswith("/"):
        return path.rstrip("/") or "/"
    return path


def is_public(path: str) -> bool:
    return normalize_path(path) in PUBLIC_PATHS


def bearer_token(authorization: str | None) -> str | None:
    if not authorization:
        return None
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer":
        return None
    return token.strip() or None


async def auth_guard(request, call_next):  # noqa: ANN001, ANN201
    """Deny-by-default HTTP guard. See the module docstring for why it exists
    alongside the per-route dependencies rather than instead of them."""
    path = request.url.path
    # CORS preflight carries no credentials by definition; the browser sends the
    # real, authenticated request straight after. Blocking it would break the
    # SPA without preventing anything.
    if request.method == "OPTIONS":
        return await call_next(request)
    if is_public(path):
        return await call_next(request)
    token = bearer_token(request.headers.get("authorization"))
    if auth_service.access_token_valid(token):
        return await call_next(request)
    # A run-scoped credential grant is hub-issued but is deliberately not an
    # access token (ADR 0009), so this backstop has to recognise it or it would
    # refuse one before any route dependency ran. It does **not** widen what a
    # grant can reach: this layer only asks "did we issue this?", and
    # ``require_credential_grant`` — wired to three routes — decides the rest.
    if auth_service.agent_grant_valid(token):
        return await call_next(request)
    return JSONResponse({"detail": "Not authenticated"}, status_code=401)
