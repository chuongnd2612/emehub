"""Pytest fixtures for the backend suite.

Every test runs against its own on-disk SQLite database, built by running the
real Alembic migrations — schema creation always goes through the same path
production uses, so a missing migration fails the suite rather than passing on a
``create_all`` shortcut.

The two secrets are set here, *before* ``app.config`` is imported, because
importing it with either one missing is a hard failure by design (ADR 0005).
They are obviously different from each other — several tests assert exactly
that separation.
"""

from __future__ import annotations

import os
from collections.abc import Iterator

import pytest

# Must precede any `app.*` import: app.config builds its singleton at import time.
TEST_JWT_SECRET = "test-jwt-secret-not-the-encryption-key"
TEST_ENCRYPTION_KEY = "test-encryption-key-not-the-jwt-secret"
os.environ.setdefault("EMEHUB_JWT_SECRET", TEST_JWT_SECRET)
os.environ.setdefault("EMEHUB_ENCRYPTION_KEY", TEST_ENCRYPTION_KEY)
os.environ.setdefault("EMEHUB_ADMIN_EMAIL", "")
os.environ.setdefault("EMEHUB_ADMIN_PASSWORD", "")


@pytest.fixture
def workspace_dir(tmp_path, monkeypatch) -> Iterator:
    """Point the app at a temp workspace + SQLite DB and rebind the singletons."""
    ws = tmp_path / "workspace"
    ws.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("EMEHUB_WORKSPACE_DIR", str(ws))
    monkeypatch.setenv("EMEHUB_DATABASE_URL", f"sqlite:///{(ws / 'test.db').as_posix()}")

    import app.config as config_module

    config_module.get_settings.cache_clear()
    fresh = config_module.get_settings()
    # Mutate the singleton in place so modules that did
    # `from app.config import settings` at import time see the temp workspace.
    config_module.settings.__dict__.update(fresh.__dict__)
    settings = config_module.settings
    settings.ensure_dirs()

    import app.db as db_module

    monkeypatch.setattr(db_module, "settings", settings)
    new_engine = db_module.create_engine(
        settings.database_url, connect_args={"check_same_thread": False}, echo=False
    )
    monkeypatch.setattr(db_module, "engine", new_engine)
    monkeypatch.setattr(
        db_module,
        "SessionLocal",
        db_module.sessionmaker(
            bind=new_engine, autoflush=False, autocommit=False, expire_on_commit=False
        ),
    )

    db_module.init_db()
    yield ws


@pytest.fixture
def db_session(workspace_dir):
    import app.db as db_module

    session = db_module.SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def app(workspace_dir):
    from app.main import create_app

    return create_app()


@pytest.fixture
def client(app, db_session):
    """TestClient wired to the isolated DB. ``get_db`` is overridden to the
    shared session so request writes and test assertions see one database."""
    from fastapi.testclient import TestClient

    from app.db import get_db

    def _override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def make_user(db_session):
    """Factory creating a real user row with an argon2 password hash."""
    from app.models.user import User
    from app.services import auth_service

    def _make(
        email: str = "member@emesoft.net",
        password: str = "correct horse battery",
        role: str = "member",
        active: bool = True,
    ):
        user = User(
            email=auth_service.normalize_email(email),
            first_name="Test",
            last_name="User",
            role=role,
            password_hash=auth_service.hash_password(password) if password else "",
            is_active=active,
        )
        db_session.add(user)
        db_session.commit()
        db_session.refresh(user)
        return user

    return _make


@pytest.fixture
def login(client):
    """Log a user in and return the parsed body (tokens + user)."""

    def _login(email: str, password: str, **extra):
        response = client.post(
            "/auth/login", json={"email": email, "password": password, **extra}
        )
        assert response.status_code == 200, response.text
        return response.json()

    return _login


@pytest.fixture
def auth_headers(login):
    """``Authorization`` header carrying a hub-audience access token."""

    def _headers(email: str, password: str, **extra):
        body = login(email, password, **extra)
        return {"Authorization": f"Bearer {body['accessToken']}"}

    return _headers
