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
from typing import Annotated
from urllib.parse import urlsplit

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

# ``api/`` — the directory holding pyproject.toml, alembic.ini and migrations/.
API_DIR = Path(__file__).resolve().parent.parent

#: Origins allowed when ``EMEHUB_CORS_ORIGINS`` is unset or empty — the hub's
#: own dev server. Agent origins are added per deployment (ADR 0008).
DEFAULT_CORS_ORIGINS = ("http://localhost:5180", "http://127.0.0.1:5180")

# The hub's own audience. Always registered; a token for the hub's API carries
# this value. Agent audiences are registered only when their URL is configured
# (see ``Settings.registered_audiences``) — INTEGRATION.md §2.
AUDIENCE_HUB = "emehub"
AUDIENCE_QAGENT = "qagent"
AUDIENCE_DAGENT = "dagent"

#: Hard ceiling on ``agent_grant_ttl_minutes`` (24h). A grant is the longest-lived
#: credential-bearing token the hub issues, so its lifetime is bounded in code and
#: not left to an operator's env var alone (ADR 0009).
GRANT_TTL_CAP_MINUTES = 1440


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
    #: Lifetime of a run-scoped Claude-credential grant (ADR 0009). Longer than an
    #: access token because an agent's background run outlives one and has no way
    #: to refresh; safe to be longer because the grant reaches only the credential
    #: routes and dies with its hub session. Clamped to
    #: :data:`GRANT_TTL_CAP_MINUTES` — a longer run mints a second grant, which
    #: needs a live session, and that pressure is the point.
    #:
    #: Deliberately **not** disable-able: there is no configuration in which this
    #: becomes an authentication bypass (CLAUDE.md › Never fail open). An operator
    #: who does not want grants has agents that never ask for one.
    agent_grant_ttl_minutes: int = 240

    # ── Registered agents ──────────────────────────────────────────────────
    agent_qagent_url: str = "http://localhost:5174"
    agent_dagent_url: str = "http://localhost:3000"

    # ── First admin (seeded on first boot only) ────────────────────────────
    admin_email: str = ""
    admin_password: str = ""

    # ── Misc ───────────────────────────────────────────────────────────────
    log_level: str = "info"
    workspace_dir: str = "./workspace"

    # ── Knowledge builds (ADR 0007 — builds run on the hub) ────────────────
    #: The Claude Code CLI executable. Baked into the image; overridable for a
    #: host install at a different path.
    claude_bin: str = "claude"
    #: Model every hub-run Claude call uses. Matches QAgent's default so the two
    #: stacks produce comparable knowledge.
    claude_model: str = "claude-sonnet-5"
    #: Default per-call CLI budget.
    claude_timeout_s: int = 300
    #: A knowledge build traverses a whole repository, so it gets its own,
    #: much longer, budget. A CLI that exceeds it lands the row in ``error``.
    claude_bootstrap_timeout_s: int = 1200
    #: Ceiling on a single ``git clone``/``fetch``.
    clone_timeout_s: int = 180
    #: **Process-wide** cap on concurrent knowledge builds. A build is minutes
    #: long, clones a repository and runs a Claude CLI process, so an uncapped
    #: queue lets one member exhaust the workspace's CPU and disk. Builds over
    #: the cap wait their turn with the row left in ``indexing``; they are never
    #: dropped. Raise it only with the container's CPU/disk in mind.
    knowledge_build_concurrency: int = 2
    #: How often a running build may write its progress back to the row
    #: (issue #68). A Claude stream emits an event every few hundred
    #: milliseconds, so persisting each one would mean thousands of UPDATEs per
    #: build; coalescing to this interval keeps the message live — the UI polls
    #: at 2s — at a handful of writes per minute. A **stage change always writes
    #: immediately**: that is the signal, not the noise.
    knowledge_progress_interval_s: float = 1.5
    #: After this long with no heartbeat, a row still sitting at ``indexing`` is
    #: reported as orphaned — whatever was building it is gone. Comfortably above
    #: both the progress interval and the queue heartbeat, so a merely slow build
    #: is never called abandoned.
    knowledge_build_stale_s: int = 120
    #: Directory holding ``<skill>/SKILL.md``. Empty means the repo's own
    #: ``skills/`` (``/app/skills`` in the image — see api/Dockerfile).
    skills_dir: str = ""

    # ── CORS ───────────────────────────────────────────────────────────────
    # The hub's own SPA is same-origin in every packaged deployment (nginx
    # proxies /api), but **an agent's origin is not**: the sign-in hand-off has
    # the agent's browser call POST /auth/agent-token cross-origin with
    # credentials (ADR 0008). So every agent origin must be listed here in any
    # deployment using the hand-off — not just for `npm run dev`.
    #
    # Accepts a JSON array or a comma-separated list; see the validator below.
    cors_origins: Annotated[list[str], NoDecode] = list(DEFAULT_CORS_ORIGINS)

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_origins(cls, value: object) -> object:
        """Accept ``a,b`` as well as ``["a","b"]``, and treat empty as unset.

        Two operator-facing traps this closes:

        * Without it, pydantic-settings decodes the env value as JSON, so a
          perfectly reasonable ``EMEHUB_CORS_ORIGINS=https://a,https://b``
          aborts startup with ``error parsing value for field "cors_origins"``
          — which names the field but not the cause.
        * ``docker-compose.yml`` passes ``${EMEHUB_CORS_ORIGINS:-}``, so an
          operator who has not set it hands us an **empty string**. That must
          mean "unset", not "allow no origins at all" — otherwise merely
          declaring the variable in compose would silently break `npm run dev`
          against the containerised API.
        """
        if isinstance(value, str):
            text = value.strip()
            if not text:
                return list(DEFAULT_CORS_ORIGINS)
            if text.startswith("["):
                import json

                return json.loads(text)
            return [part.strip() for part in text.split(",") if part.strip()]
        return value

    @field_validator("agent_grant_ttl_minutes")
    @classmethod
    def _cap_grant_ttl(cls, value: int) -> int:
        """Refuse an out-of-range grant lifetime rather than silently clamping it.

        Startup failure, not a warning: an operator who typed ``14400`` meaning
        minutes-not-hours should learn about it now, and a hub that quietly ran
        with a different lifetime than configured would be worse than one that
        would not start.
        """
        if value < 1 or value > GRANT_TTL_CAP_MINUTES:
            raise ValueError(
                f"EMEHUB_AGENT_GRANT_TTL_MINUTES must be between 1 and "
                f"{GRANT_TTL_CAP_MINUTES} (got {value}). A credential grant is the "
                "longest-lived credential-bearing token the hub issues (ADR 0009)."
            )
        return value

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

    def agent_url(self, audience: str) -> str:
        """The configured origin for ``audience``, or ``""`` when unset."""
        mapping = {
            AUDIENCE_QAGENT: self.agent_qagent_url,
            AUDIENCE_DAGENT: self.agent_dagent_url,
        }
        return (mapping.get(audience) or "").strip()

    def handoff_ready(self, audience: str) -> bool:
        """Whether the sign-in hand-off can actually work for ``audience``.

        Registration (a URL) is necessary but **not sufficient**: the hand-off
        also needs the refresh cookie to reach the agent's origin, which requires
        ``EMEHUB_COOKIE_DOMAIN`` to be set to a domain the agent is a subdomain
        of (ADR 0008). Without that the browser never sends the cookie and the
        agent's call fails — so a UI that offered a launch would be lying.

        Kept deliberately distinct from ``registered_audiences`` so "a URL is
        set" can never silently come to mean "single sign-on works".
        """
        url = self.agent_url(audience)
        if not url or audience not in self.registered_audiences:
            return False
        domain = (self.cookie_domain or "").strip().lstrip(".").lower()
        if not domain:
            return False
        host = urlsplit(url if "//" in url else f"//{url}").hostname or ""
        host = host.lower()
        return host == domain or host.endswith(f".{domain}")

    def handoff_blocker(self, audience: str) -> str | None:
        """Why the hand-off is unavailable for ``audience`` — ``None`` if it is.

        Returned to the UI so a disabled launch button can name the missing
        configuration instead of just being dead.
        """
        if not self.agent_url(audience):
            return "no_url"
        if not (self.cookie_domain or "").strip():
            return "no_cookie_domain"
        if not self.handoff_ready(audience):
            return "domain_mismatch"
        return None

    @property
    def workspace_path(self) -> Path:
        path = Path(self.workspace_dir)
        return path if path.is_absolute() else (API_DIR / path).resolve()

    @property
    def skills_path(self) -> Path:
        """Where ``<skill>/SKILL.md`` lives — the repo root's ``skills/``."""
        if (self.skills_dir or "").strip():
            path = Path(self.skills_dir)
            return path if path.is_absolute() else (API_DIR / path).resolve()
        return API_DIR.parent / "skills"

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
