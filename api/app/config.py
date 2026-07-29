"""Configuration, read from the environment with the ``EMEHUB_`` prefix.

Security rules (CLAUDE.md, ADR 0005) enforced here:

* ``EMEHUB_JWT_SECRET`` and ``EMEHUB_ENCRYPTION_KEY`` are TWO different secrets
  and both are required. A missing one is a hard startup failure.
* **No boot-time secret generation.** A generated fallback encryption key
  silently creates rows that cannot be decrypted after the next restart, so
  there is deliberately no default.
* The two must not be equal — reusing one for the other defeats the split.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# ``api/`` — the directory holding pyproject.toml, alembic.ini and migrations/.
API_DIR = Path(__file__).resolve().parent.parent

# The hub's own audience. Always registered; a token for the hub's API carries
# this value. Agent audiences are registered only when their URL is configured
# (see ``Settings.registered_audiences``) — INTEGRATION.md §2.
AUDIENCE_HUB = "emehub"
AUDIENCE_QAGENT = "qagent"
AUDIENCE_DAGENT = "dagent"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="EMEHUB_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ── Secrets (required, no defaults — see the module docstring) ──────────
    jwt_secret: str = Field(min_length=1)
    encryption_key: str = Field(min_length=1)

    # ── Database ───────────────────────────────────────────────────────────
    database_url: str = "postgresql+psycopg://postgres:postgres@localhost:5457/emehub"
    db_port: int = 5457

    # ── Ports ──────────────────────────────────────────────────────────────
    host: str = "127.0.0.1"
    api_port: int = 8790
    web_port: int = 5180

    # ── Tokens & cookies ───────────────────────────────────────────────────
    access_token_ttl_minutes: int = 15
    refresh_token_ttl_days: int = 30
    cookie_secure: bool = False
    cookie_domain: str = ""
    # The SPA reaches the API through a ``/api`` prefix (nginx strips it, the Vite
    # dev proxy rewrites it), so a cookie scoped to ``/auth`` would never be sent
    # back on ``/api/auth/refresh``. Default to the site root; narrow it per
    # deployment if the hub is ever served without the prefix.
    cookie_path: str = "/"
    mfa_token_ttl_minutes: int = 5
    reset_token_ttl_minutes: int = 30

    # ── Registered agents ──────────────────────────────────────────────────
    agent_qagent_url: str = "http://localhost:5174"
    agent_dagent_url: str = "http://localhost:3000"

    # ── First admin (seeded on first boot only) ────────────────────────────
    admin_email: str = ""
    admin_password: str = ""

    # ── Misc ───────────────────────────────────────────────────────────────
    log_level: str = "info"
    workspace_dir: str = "./workspace"

    # ── CORS ───────────────────────────────────────────────────────────────
    # The SPA is same-origin in every packaged deployment (nginx proxies /api),
    # so this only matters for `npm run dev` against a locally-run API.
    cors_origins: list[str] = ["http://localhost:5180", "http://127.0.0.1:5180"]

    @model_validator(mode="after")
    def _secrets_must_differ(self) -> "Settings":
        if self.jwt_secret == self.encryption_key:
            raise ValueError(
                "EMEHUB_JWT_SECRET and EMEHUB_ENCRYPTION_KEY must be two different "
                "secrets — never derive or reuse one for the other (ADR 0005)."
            )
        return self

    # ── Derived ────────────────────────────────────────────────────────────
    @property
    def registered_audiences(self) -> tuple[str, ...]:
        """Audiences the hub will mint an access token for (INTEGRATION.md §2).

        The hub itself is always registered. An agent is registered only when
        its URL is configured — an agent the operator has not declared must not
        receive a token, so this is the single allowlist every token-issuing
        path consults.
        """
        out = [AUDIENCE_HUB]
        if (self.agent_qagent_url or "").strip():
            out.append(AUDIENCE_QAGENT)
        if (self.agent_dagent_url or "").strip():
            out.append(AUDIENCE_DAGENT)
        return tuple(out)

    @property
    def workspace_path(self) -> Path:
        path = Path(self.workspace_dir)
        return path if path.is_absolute() else (API_DIR / path).resolve()

    def ensure_dirs(self) -> None:
        self.workspace_path.mkdir(parents=True, exist_ok=True)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Load settings once. Raises at import/startup if a secret is missing."""
    return Settings()  # type: ignore[call-arg]


# Module-level singleton, so `from app.config import settings` works everywhere
# and the test harness can rebind fields in place. Importing this module with a
# missing secret raises — the app refuses to start rather than booting insecurely.
settings = get_settings()
