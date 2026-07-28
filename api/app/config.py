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

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


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

    # ── Registered agents ──────────────────────────────────────────────────
    agent_qagent_url: str = "http://localhost:5174"
    agent_dagent_url: str = "http://localhost:3000"

    # ── First admin (seeded on first boot only) ────────────────────────────
    admin_email: str = ""
    admin_password: str = ""

    # ── Misc ───────────────────────────────────────────────────────────────
    log_level: str = "info"
    workspace_dir: str = "./workspace"

    @model_validator(mode="after")
    def _secrets_must_differ(self) -> "Settings":
        if self.jwt_secret == self.encryption_key:
            raise ValueError(
                "EMEHUB_JWT_SECRET and EMEHUB_ENCRYPTION_KEY must be two different "
                "secrets — never derive or reuse one for the other (ADR 0005)."
            )
        return self


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Load settings once. Raises at import/startup if a secret is missing."""
    return Settings()  # type: ignore[call-arg]
