"""EmeHub API.

Phase 1 skeleton: only ``/health`` exists. Every screen in ``app/`` reads from
the typed stub layer at ``app/src/data/`` until the real endpoints land here —
each stub carries a ``# STUB:`` comment naming the route that will replace it.

Importing this module loads the settings, so a missing ``EMEHUB_JWT_SECRET`` or
``EMEHUB_ENCRYPTION_KEY`` refuses to start rather than booting insecurely.
"""

from __future__ import annotations

from fastapi import FastAPI

from app.config import get_settings

# Fail fast at import time if a required secret is absent.
settings = get_settings()

app = FastAPI(
    title="EmeHub API",
    version="0.1.0",
    description="EMESOFT AI Operating Center — identity and shared configuration.",
)


@app.get("/health")
def health() -> dict[str, str]:
    """Liveness probe. Returns no configuration and never a secret."""
    return {"status": "ok", "service": "emehub-api", "version": "0.1.0"}
