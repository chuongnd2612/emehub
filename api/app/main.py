"""EmeHub API — application factory and entrypoint.

Importing this module loads the settings, so a missing ``EMEHUB_JWT_SECRET`` or
``EMEHUB_ENCRYPTION_KEY`` refuses to start rather than booting insecurely
(ADR 0005). There is no generated-on-boot fallback for either.

## Auth posture

Routers are registered from one table, :data:`ROUTERS`, and each row declares
its own posture:

* ``PUBLIC``    — no blanket dependency. Only ``health``; every path it exposes
  is also in ``security.PUBLIC_PATHS``.
* ``MIXED``     — the auth router, which straddles the boundary: its public
  endpoints are individually allowlisted, its protected ones each declare
  ``Depends(require_user)`` or ``Depends(require_admin)``.
* ``CONTRACT``  — the endpoints agents consume (INTEGRATION.md §3), registered
  with ``Depends(require_principal)``: any *registered* audience is accepted,
  because an agent calls them with the token it holds (``aud: "qagent"``), not a
  hub token. An unregistered audience is still refused.
* ``GRANTED``   — ``CONTRACT``, and additionally accepts a run-scoped credential
  grant (ADR 0009), registered with ``Depends(require_credential_grant)``. Only
  ``credentials``. The blanket has to be the *loosest* dependency a router needs,
  because every route's own dependency runs on top and the stricter one decides —
  so a grant reaching this router still cannot manage a credential.
* ``PROTECTED`` — everything else, registered with a blanket
  ``Depends(require_user)`` (``aud: "emehub"`` only).

On top of that, ``security.auth_guard`` refuses any request that is neither
allowlisted nor carrying a valid hub-issued token. See ``app/security.py`` for
why both layers exist. Neither has an off switch.
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.audit_context import bind_audit_actor
from app.config import settings
from app.db import init_db
from app.deps_auth import require_credential_grant, require_principal, require_user
from app.logging import logger, setup_logging
from app.routers import (
    agents,
    audit,
    auth,
    connections,
    credentials,
    dagent,
    health,
    me,
    projects,
    saved_queries,
    tickets,
)
from app.security import auth_guard

VERSION = "0.1.0"

PUBLIC = "public"
MIXED = "mixed"
CONTRACT = "contract"
GRANTED = "granted"
PROTECTED = "protected"

#: (module, posture). Adding a router here is the only registration step, and
#: omitting a posture is impossible — so a new router cannot be accidentally
#: public.
ROUTERS = (
    (health, PUBLIC),
    (auth, MIXED),
    # PROTECTED: the launch registry is the hub UI's own, aud: emehub only.
    # An agent has no business enumerating its siblings, so this is not in
    # the contract and an agent token is refused.
    (agents, PROTECTED),
    (me, CONTRACT),
    (audit, CONTRACT),
    # GET /connections is in the contract (INTEGRATION.md §3), so an agent's own
    # token must reach it; every other route in that router adds
    # Depends(require_user) so managing a connection stays hub-only.
    (connections, CONTRACT),
    # GRANTED, not CONTRACT: `/resolve`, `/refreshed` and `/usage` are called by
    # an agent with its own token *or* with a run-scoped credential grant, which a
    # background run past the 15-minute token expiry has to use (ADR 0009). Every
    # management endpoint in that router declares its own require_user/require_admin
    # on top, so neither a bare agent token nor a grant can manage a credential.
    (credentials, GRANTED),
    # CONTRACT: GET /projects, GET …/config, GET …/knowledge and PATCH …/knowledge
    # are called by an agent with its own token (aud: "qagent"). The router's
    # non-contract writes each add Depends(require_user) to stay hub-only.
    (projects, CONTRACT),
    # Agents read the ticket store with the token they hold (aud: qagent/dagent),
    # so it cannot be hub-audience-only — INTEGRATION.md §3.
    (tickets, CONTRACT),
    # CONTRACT for the same reason: an agent that builds and runs queries has the
    # same reason to read a saved one. Scoped own + shared like everything else.
    (saved_queries, CONTRACT),
    # CONTRACT: DAgent's own surface, under its own /dagent prefix. It is called
    # with a token whose aud is "dagent", so require_user would refuse the only
    # caller it exists for; every route inside is scoped through
    # get_owned_or_404 exactly like the connections router.
    #
    # Registered last and kept entirely separate on purpose. DAgent needs a wider
    # provider surface than anything else here — pull requests above all — and
    # widening the shared routers to serve it would change endpoints QAgent and
    # the hub UI already depend on. This router adds routes and modifies none, so
    # a deployment that never calls /dagent/* behaves exactly as it did before.
    (dagent, CONTRACT),
)

_POSTURE_DEPENDENCY = {
    PUBLIC: None,
    MIXED: None,  # each route declares its own
    CONTRACT: require_principal,
    GRANTED: require_credential_grant,
    PROTECTED: require_user,
}


def _seed_admin() -> None:
    """Ensure the first administrator exists, from the configured credentials.

    Unlike QAgent there is **no dev fallback that generates a password**: a
    generated credential is a secret created at boot, which CLAUDE.md forbids.
    If the variables are unset and the workspace has no users, the hub boots and
    logs loudly that nobody can sign in — it does not invent a way in.
    """
    from app.db import SessionLocal
    from app.models.user import ROLE_ADMIN, User
    from app.services import auth_service

    db = SessionLocal()
    try:
        if db.query(User.id).first() is not None:
            return
        email = auth_service.normalize_email(settings.admin_email)
        password = settings.admin_password
        if not (email and password):
            logger.error(
                "No users exist and no first admin is configured — set "
                "EMEHUB_ADMIN_EMAIL and EMEHUB_ADMIN_PASSWORD to create one. "
                "Nobody can sign in until you do."
            )
            return
        db.add(
            User(
                email=email,
                first_name="Admin",
                last_name="",
                role=ROLE_ADMIN,
                password_hash=auth_service.hash_password(password),
                is_active=True,
            )
        )
        db.commit()
        logger.info("Seeded first admin %s", email)
    except Exception as exc:  # noqa: BLE001 - never block startup on the seed
        logger.warning("admin seed failed: %s", exc)
        db.rollback()
    finally:
        db.close()


@asynccontextmanager
async def lifespan(app: FastAPI):  # noqa: ARG001
    setup_logging()
    settings.ensure_dirs()
    init_db()  # Alembic upgrade → head, on every boot.
    _seed_admin()
    logger.info(
        "EmeHub API ready on %s:%s — audiences: %s",
        settings.host,
        settings.api_port,
        ", ".join(settings.registered_audiences),
    )
    yield


def create_app() -> FastAPI:
    app = FastAPI(
        title="EmeHub API",
        version=VERSION,
        description="EMESOFT AI Operating Center — identity and shared configuration.",
        lifespan=lifespan,
    )

    # Registered before CORS so CORS stays the outermost middleware and its
    # headers are attached even to the guard's 401s.
    app.middleware("http")(auth_guard)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        # Any localhost port, so `npm run dev` works when Vite falls off 5180.
        allow_origin_regex=r"http://(localhost|127\.0\.0\.1):\d+",
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    for module, posture in ROUTERS:
        # bind_audit_actor runs in the endpoint's request context (a
        # BaseHTTPMiddleware would run in a different one and lose the value),
        # so audit events are attributed to the caller without threading the
        # user through every service call.
        dependencies = [Depends(bind_audit_actor)]
        guard = _POSTURE_DEPENDENCY[posture]  # KeyError on an unknown posture
        if guard is not None:
            dependencies.append(Depends(guard))
        app.include_router(module.router, dependencies=dependencies)

    return app


app = create_app()
