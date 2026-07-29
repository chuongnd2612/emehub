"""Application logging.

Deliberately stdlib-only — the hub has no need for a logging dependency, and one
fewer package in the image is one fewer thing to audit.

**Nothing here may ever be handed a secret.** Tokens, PATs, refresh tokens and
the two ``EMEHUB_*`` secrets are never logged (CLAUDE.md › Security rules).
"""

from __future__ import annotations

import logging
import sys

from app.config import settings

logger = logging.getLogger("emehub")

_LEVELS = {
    "debug": logging.DEBUG,
    "info": logging.INFO,
    "warning": logging.WARNING,
    "error": logging.ERROR,
}


def setup_logging() -> None:
    """Configure the root logger once, at the configured level."""
    level = _LEVELS.get((settings.log_level or "info").strip().lower(), logging.INFO)
    root = logging.getLogger()
    root.setLevel(level)
    if not any(getattr(h, "_emehub", False) for h in root.handlers):
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)-8s %(name)s: %(message)s")
        )
        handler._emehub = True  # type: ignore[attr-defined]
        root.addHandler(handler)
    logger.setLevel(level)
