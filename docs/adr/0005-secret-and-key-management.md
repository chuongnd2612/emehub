# ADR 0005 — Separate the signing secret from the encryption key

- **Status:** Accepted
- **Date:** 2026-07-28

## Context

QAgent has one secret, `QAGENT_SECRET_KEY`, and it does two unrelated jobs:

1. It signs and verifies JWTs — `api/app/services/auth_service.py` passes
   `settings.secret_key` to HS256.
2. It derives the symmetric encryption key for everything stored encrypted at rest —
   `api/app/crypto.py` builds a Fernet key from `sha256(settings.secret_key)`. That covers
   Claude credentials, provider PATs and project test-account passwords.

For a single application this is merely untidy. For the migration in
[ADR 0001](0001-emehub-is-the-source-of-truth.md) it is a real obstacle:

- **Phase 2 moves authentication to the hub but leaves credentials in QAgent.** If the hub
  needs the signing secret and QAgent needs the same value to decrypt its rows, the secret has
  to exist in both services — one secret, two blast radii, and neither can rotate it.
- **Rotating either capability rotates both.** Changing the signing secret to invalidate
  tokens would make every encrypted row undecryptable. In practice this means the secret can
  never be rotated at all, which is the opposite of what a signing secret is for.
- The two jobs have genuinely different lifecycles. A signing secret should rotate often and
  cheaply; losing it logs everyone out. An encryption key must never be lost; losing it
  destroys data.

## Decision

The hub uses **two separate secrets from day one**:

| Variable | Job | Rotation |
|---|---|---|
| `EMEHUB_JWT_SECRET` | Signs access tokens. Replaced by an RS256 key pair in Phase 3 ([INTEGRATION.md](../INTEGRATION.md#key-distribution)). | Rotatable. Worst case: everyone re-authenticates. |
| `EMEHUB_ENCRYPTION_KEY` | Encrypts credentials and secrets at rest. | Rotation is a re-key operation over the data. Loss is unrecoverable. |

Neither has a default. The application **refuses to start** if either is missing — no
generated-on-boot fallback, because a fallback encryption key silently produces rows nobody
can decrypt after the next restart.

`EMEHUB_ENCRYPTION_KEY` is never sent to an agent, never logged, and never returned by any
endpoint.

## Consequences

**Good.** Tokens can be invalidated by rotating the signing secret without touching stored
credentials. When Phase 3 moves to RS256 + JWTs, only the signing side changes. The two
secrets can be stored with different handling — the encryption key deserves backup, the
signing secret does not.

**Cost — the QAgent credential migration is a re-key, not a copy.** Every encrypted value in
QAgent is Fernet-encrypted under `sha256(QAGENT_SECRET_KEY)`. The hub uses a different key.
Phase 3 therefore needs a one-shot migration that:

- runs with **both** secrets available;
- decrypts each row with the old key and re-encrypts with the new;
- is idempotent, so a partial run can be resumed (the `enc::` prefix helps distinguish
  already-migrated values, but the ciphertext alone does not say which key it used — carry an
  explicit key-version marker rather than guessing);
- is rehearsed against a database copy before it touches the live one;
- is preceded by a backup that is verified restorable, because a mistake here loses every
  stored credential in the suite.

**Follow-up for QAgent.** Splitting `QAGENT_SECRET_KEY` into two variables in QAgent *before*
Phase 3 would make the migration simpler and is worth doing on its own merits. Filed as a
QAgent concern, not a hub one.

**Deferred.** Where the secrets live in production — environment variables today, a secrets
manager eventually. Not decided here; the decision above holds either way.
