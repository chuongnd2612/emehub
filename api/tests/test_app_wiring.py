"""App wiring: the boot path, the allowlist, and the admin seed.

These are the tests that would fail if someone widened the public surface or
reintroduced a fail-open path.
"""

from __future__ import annotations

import pytest

from app import security

from conftest import MIN_EXPECTED_ROUTES, api_routes


def test_route_discovery_actually_finds_routes(app):
    """Guard for the guard.

    ``test_every_route_is_either_allowlisted_or_guarded`` below is a loop with
    an ``assert x == []`` at the end: if discovery yields nothing, it passes
    while checking nothing. It did exactly that for a while — it walked
    ``app.routes`` flat, but ``include_router`` nests routes under an
    ``_IncludedRouter`` in this FastAPI version, so it inspected **zero** of
    them. This test exists so that failure mode is loud.
    """
    assert len(api_routes(app)) >= MIN_EXPECTED_ROUTES


def test_every_route_is_either_allowlisted_or_guarded(app):
    """No route may be reachable without authentication unless it is one of the
    handful of explicitly public paths."""
    from app.deps_auth import require_admin, require_principal, require_user

    guards = {require_user, require_admin, require_principal}
    routes = api_routes(app)
    assert len(routes) >= MIN_EXPECTED_ROUTES, "route discovery is broken"

    unguarded = []
    for route in routes:
        if security.is_public(route.path):
            continue
        callables = {d.call for d in route.dependant.dependencies}
        # Nested dependencies (require_admin → require_user) count too.
        for dependency in route.dependant.dependencies:
            callables.update(sub.call for sub in dependency.dependencies)
        if not (callables & guards):
            unguarded.append(f"{sorted(route.methods)} {route.path}")
    assert unguarded == []


def test_the_allowlist_is_exactly_the_expected_paths():
    assert security.PUBLIC_PATHS == frozenset(
        {
            "/health",
            "/auth/login",
            "/auth/login/mfa",
            "/auth/refresh",
            "/auth/request-reset",
            "/auth/reset",
            "/openapi.json",
            "/docs",
            "/docs/oauth2-redirect",
            "/redoc",
        }
    )


def test_the_allowlist_matches_exactly_never_by_prefix():
    assert security.is_public("/health") is True
    assert security.is_public("/health/") is True
    assert security.is_public("/auth/login") is True
    # A prefix match here would expose every future /auth/* endpoint.
    assert security.is_public("/auth/users") is False
    assert security.is_public("/auth/login/../users") is False
    assert security.is_public("/healthz") is False


def test_secrets_must_be_two_different_values():
    """ADR 0005 — the config refuses a single shared secret outright."""
    import app.config as config_module

    with pytest.raises(ValueError, match="two different"):
        config_module.Settings(jwt_secret="same", encryption_key="same")


def test_a_missing_secret_refuses_to_start(monkeypatch):
    """No boot-time generation: an absent secret is a hard failure."""
    import app.config as config_module

    monkeypatch.delenv("EMEHUB_ENCRYPTION_KEY", raising=False)
    monkeypatch.setenv("EMEHUB_JWT_SECRET", "present")
    with pytest.raises(Exception):
        config_module.Settings(_env_file=None)  # type: ignore[call-arg]


def test_seed_admin_creates_the_first_administrator(workspace_dir, monkeypatch):
    import app.config as config_module
    import app.db as db_module
    from app.main import _seed_admin
    from app.models.user import ROLE_ADMIN, User

    monkeypatch.setattr(config_module.settings, "admin_email", "First.Admin@Emesoft.net")
    monkeypatch.setattr(config_module.settings, "admin_password", "password12345")
    _seed_admin()

    db = db_module.SessionLocal()
    try:
        user = db.query(User).one()
        assert user.email == "first.admin@emesoft.net"
        assert user.role == ROLE_ADMIN
        assert user.password_hash.startswith("$argon2")
        assert user.password_hash != "password12345"
    finally:
        db.close()

    # Idempotent — a second boot does not add another user.
    _seed_admin()
    db = db_module.SessionLocal()
    try:
        assert db.query(User).count() == 1
    finally:
        db.close()


def test_seed_admin_never_invents_a_password(workspace_dir, monkeypatch, caplog):
    """QAgent generates a dev password when none is configured. The hub does
    not — that is a secret created at boot (CLAUDE.md)."""
    import logging

    import app.config as config_module
    import app.db as db_module
    from app.main import _seed_admin
    from app.models.user import User

    monkeypatch.setattr(config_module.settings, "admin_email", "")
    monkeypatch.setattr(config_module.settings, "admin_password", "")
    with caplog.at_level(logging.ERROR, logger="emehub"):
        _seed_admin()

    db = db_module.SessionLocal()
    try:
        assert db.query(User).count() == 0
    finally:
        db.close()
    assert "EMEHUB_ADMIN_EMAIL" in caplog.text


def test_migrations_created_every_table(workspace_dir):
    """The schema comes from Alembic, not create_all — a table missing from a
    migration fails here."""
    from sqlalchemy import inspect

    import app.db as db_module

    tables = set(inspect(db_module.engine).get_table_names())
    assert {"users", "auth_sessions", "audit_logs", "alembic_version"} <= tables


def test_every_migration_id_fits_the_alembic_version_column():
    """`alembic_version.version_num` is `varchar(32)` and Alembic creates it at
    that width. An over-long revision id runs the DDL and then fails on the
    stamp — Postgres only, because SQLite does not enforce VARCHAR length, so
    the whole test suite goes green and the container refuses to boot.

    That happened once (0006). This is the guard.
    """
    from pathlib import Path

    versions = Path(__file__).resolve().parents[1] / "migrations" / "versions"
    ids = []
    for path in sorted(versions.glob("*.py")):
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.startswith("revision: str"):
                ids.append((path.name, line.split("=", 1)[1].strip().strip('"')))
                break

    assert ids, "no migrations found — the glob is wrong, not the migrations"
    too_long = [(name, rid, len(rid)) for name, rid in ids if len(rid) > 32]
    assert not too_long, f"revision ids over 32 chars: {too_long}"


def test_openapi_builds(client):
    assert client.get("/openapi.json").status_code == 200
