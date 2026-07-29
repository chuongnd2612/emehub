"""Crypto — the ADR 0005 separation, proven rather than asserted in a comment.

The point of these tests is the negative one: a value encrypted under
``EMEHUB_ENCRYPTION_KEY`` must **not** decrypt under ``EMEHUB_JWT_SECRET``. If
someone "simplifies" ``app/crypto.py`` to derive its key from the signing secret
the way QAgent does, this file fails.
"""

from __future__ import annotations

import pytest

from app import crypto


def test_round_trips_with_the_encryption_key(workspace_dir):
    secret = "ghp_averyrealisticlookingpersonalaccesstoken"
    envelope = crypto.encrypt(secret)

    assert envelope != secret
    assert secret not in envelope  # the plaintext is not hiding in the envelope
    assert crypto.decrypt(envelope) == secret


def test_envelope_carries_the_prefix_and_key_version(workspace_dir):
    envelope = crypto.encrypt("value")

    assert envelope.startswith("enc::v1:")
    assert crypto.is_encrypted(envelope)
    # The explicit key-version marker ADR 0005 requires, so a resumable re-key
    # can tell migrated rows from unmigrated ones without trying a decrypt.
    assert crypto.key_version_of(envelope) == "v1"
    assert crypto.key_version_of("plaintext") is None


def test_does_not_decrypt_under_the_jwt_secret(workspace_dir, monkeypatch):
    """The whole reason this project exists (ADR 0005 / INTEGRATION.md §6.3)."""
    import app.config as config_module

    envelope = crypto.encrypt("claude-oauth-token")

    # Pretend the encryption key had been (wrongly) set to the signing secret.
    monkeypatch.setattr(
        config_module.settings, "encryption_key", config_module.settings.jwt_secret
    )
    assert config_module.settings.jwt_secret != "", "sanity: the signing secret is set"
    assert crypto.decrypt(envelope) is None, (
        "ciphertext must not decrypt under the JWT secret — the encryption key "
        "is derived from EMEHUB_ENCRYPTION_KEY and nothing else"
    )


def test_wrong_encryption_key_yields_none_not_garbage(workspace_dir, monkeypatch):
    import app.config as config_module

    envelope = crypto.encrypt("value")
    monkeypatch.setattr(config_module.settings, "encryption_key", "a-different-key")
    assert crypto.decrypt(envelope) is None


def test_unknown_key_version_is_refused(workspace_dir):
    assert crypto.decrypt("enc::v99:gAAAAA") is None
    assert crypto.key_version_of("enc::v99:gAAAAA") == "v99"


def test_empty_and_plaintext_pass_through(workspace_dir):
    assert crypto.encrypt("") == ""
    assert crypto.encrypt(None) is None
    assert crypto.decrypt("not-encrypted") == "not-encrypted"
    assert crypto.is_encrypted("not-encrypted") is False


def test_mask_never_returns_the_value(workspace_dir):
    assert crypto.mask("supersecret") == "••••••••"
    assert crypto.mask("") == ""


def test_crypto_module_never_mentions_the_jwt_secret():
    """A grep test, deliberately. ``jwt_secret`` appearing in this module is the
    single mistake ADR 0005 exists to prevent — catch it in CI, not in review."""
    from pathlib import Path

    source = Path(crypto.__file__).read_text(encoding="utf-8")
    code = "\n".join(
        line for line in source.splitlines() if not line.strip().startswith(("#", "*"))
    )
    # Strip the module docstring (it discusses the rule at length).
    body = code.split('"""', 2)[-1]
    assert "jwt_secret" not in body
    assert "settings.encryption_key" in body


@pytest.mark.parametrize("value", ["a", "x" * 4096, "unicode ✓ ünïcödé", '{"json": true}'])
def test_round_trip_various_payloads(workspace_dir, value):
    assert crypto.decrypt(crypto.encrypt(value)) == value
