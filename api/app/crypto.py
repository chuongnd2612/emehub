"""Symmetric encryption for secrets at rest.

**Two secrets, never one** (CLAUDE.md › Security rules,
[ADR 0005](../../docs/adr/0005-secret-and-key-management.md)). The key used here
is derived from ``EMEHUB_ENCRYPTION_KEY`` and *nothing else*.
``EMEHUB_JWT_SECRET`` must never appear in this module: QAgent derives its
Fernet key from the same secret it signs JWTs with, and that single mistake is
the reason this project exists. Rotating the signing secret must not make a
single stored credential undecryptable.

## Envelope format

    enc::v1:<fernet-token>

* ``enc::`` — the self-identifying prefix, kept from QAgent so a value can be
  told apart from plaintext without consulting a schema.
* ``v1``    — an explicit **key-version marker**. ADR 0005 requires this: the
  Phase-3 re-key runs with both the old and new secrets available and must be
  idempotent, and "the ciphertext alone does not say which key it used — carry
  an explicit key-version marker rather than guessing". With the marker, a
  resumed migration can tell a migrated row from an unmigrated one by reading
  four characters instead of attempting a decrypt.

A new key version adds an entry to :data:`_DERIVERS` and bumps
:data:`CURRENT_KEY_VERSION`; old versions stay readable until the re-key
completes.
"""

from __future__ import annotations

import base64

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from app.config import settings

PREFIX = "enc::"
CURRENT_KEY_VERSION = "v1"

# Domain separation: even if some future subsystem derives another key from the
# same secret, it will use a different `info` and land on a different key.
_V1_INFO = b"emehub/encryption-key/v1"


class UnknownKeyVersion(ValueError):
    """Raised when a stored value carries a key version this build cannot read."""


def _derive_v1(secret: str) -> bytes:
    """HKDF-SHA256 over ``EMEHUB_ENCRYPTION_KEY`` → a 32-byte Fernet key."""
    raw = HKDF(
        algorithm=hashes.SHA256(), length=32, salt=None, info=_V1_INFO
    ).derive(secret.encode("utf-8"))
    return base64.urlsafe_b64encode(raw)


_DERIVERS = {"v1": _derive_v1}


def _fernet(version: str = CURRENT_KEY_VERSION) -> Fernet:
    deriver = _DERIVERS.get(version)
    if deriver is None:
        raise UnknownKeyVersion(f"No key derivation registered for version '{version}'")
    # Read the secret at call time (not import time) so the test harness and a
    # future secrets-manager refresh both see the current value. Never read
    # ``settings.jwt_secret`` here — see the module docstring.
    return Fernet(deriver(settings.encryption_key))


def _split(value: str) -> tuple[str, str]:
    """Split a stored envelope into ``(key_version, ciphertext)``."""
    body = value[len(PREFIX) :]
    version, sep, token = body.partition(":")
    if not sep:
        # Defensive: an envelope written before versioning would be v1 material.
        return CURRENT_KEY_VERSION, body
    return version, token


def encrypt(value: str | None) -> str | None:
    """Encrypt a plaintext secret into a versioned envelope.

    ``None`` and ``""`` pass through unchanged so optional columns stay empty
    rather than storing the ciphertext of nothing.
    """
    if not value:
        return value
    token = _fernet().encrypt(value.encode("utf-8")).decode("utf-8")
    return f"{PREFIX}{CURRENT_KEY_VERSION}:{token}"


def decrypt(value: str | None) -> str | None:
    """Decrypt a value produced by :func:`encrypt`.

    Returns ``None`` when the ciphertext does not authenticate under the current
    key — the caller must treat that as "unavailable", never as plaintext.
    Values without the ``enc::`` prefix pass through (they were never encrypted).
    """
    if not value:
        return value
    if not value.startswith(PREFIX):
        return value
    version, token = _split(value)
    try:
        return _fernet(version).decrypt(token.encode("utf-8")).decode("utf-8")
    except (InvalidToken, UnknownKeyVersion):
        return None


def is_encrypted(value: str | None) -> bool:
    return bool(value) and value.startswith(PREFIX)


def key_version_of(value: str | None) -> str | None:
    """The key version a stored value was written with, or ``None`` if plaintext.

    This is what makes the Phase-3 re-key resumable.
    """
    if not is_encrypted(value):
        return None
    return _split(value or "")[0]


def mask(value: str | None) -> str:
    """Render a secret for display without leaking it. Never return the value."""
    if not value:
        return ""
    return "••••••••"
