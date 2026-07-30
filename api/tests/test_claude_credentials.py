"""Claude credentials — parsing, encryption at rest, and the resolution rule.

The service-layer half of the slice. The HTTP half (posture, audience, audit,
who-can-see-what) lives in ``test_claude_credentials_api.py``.

Every test that needs a token uses :data:`TOKEN`, and several assert it does not
appear where it must not — that is the point of the slice, so it is asserted
rather than reviewed.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest

from app import crypto
from app.models.claude_credentials import (
    STATUS_ACTIVE,
    STATUS_EXPIRED,
    STATUS_EXPIRING,
    STATUS_REFRESHABLE,
    ClaudeCredentials,
)
from app.services import claude_credentials as svc

TOKEN = "sk-ant-oat01-THIS-IS-THE-SECRET"
OTHER_TOKEN = "sk-ant-oat01-A-DIFFERENT-SECRET"


def epoch_ms(days_from_now: float, now: datetime | None = None) -> int:
    reference = now or datetime.now(timezone.utc)
    return int((reference + timedelta(days=days_from_now)).timestamp() * 1000)


def creds_file(
    token: str = TOKEN,
    *,
    days: float | None = 30,
    scopes: list | None = None,
    subscription: str | None = "max",
    wrapper: str = "claudeAiOauth",
    refresh: bool = True,
) -> str:
    """A realistic ``.credentials.json``. ``wrapper=""`` produces a bare object.

    ``refresh=True`` is the default because a real file written by the Claude
    CLI always carries a refresh token — which is precisely why an elapsed
    ``expiresAt`` must not read as ``expired`` (issue #63). Pass
    ``refresh=False`` for the genuinely dead case: an access token past its
    expiry with nothing to renew it from.
    """
    oauth: dict = {"accessToken": token}
    if refresh:
        oauth["refreshToken"] = "sk-ant-ort01-refresh"
    if days is not None:
        oauth["expiresAt"] = epoch_ms(days)
    if scopes is not None:
        oauth["scopes"] = scopes
    if subscription is not None:
        oauth["subscriptionType"] = subscription
    return json.dumps(oauth if wrapper == "" else {wrapper: oauth})


# ------------------------------------------------------------------ parsing
def test_accepts_the_claude_ai_oauth_object():
    parsed = svc.parse_credentials(creds_file(scopes=["user:inference", "user:profile"]))
    assert parsed.token == TOKEN
    assert parsed.scopes == ["user:inference", "user:profile"]
    assert parsed.subscription_type == "max"
    assert parsed.expires_at is not None


def test_accepts_the_snake_case_wrapper_and_the_bare_object():
    """Mirrors ``app/src/data/credentials.ts``: ``claudeAiOauth`` |
    ``claude_ai_oauth`` | the root object."""
    assert svc.parse_credentials(creds_file(wrapper="claude_ai_oauth")).token == TOKEN
    assert svc.parse_credentials(creds_file(wrapper="")).token == TOKEN


def test_accepts_snake_case_field_names():
    raw = json.dumps({"access_token": TOKEN, "expires_at": epoch_ms(10)})
    parsed = svc.parse_credentials(raw)
    assert parsed.token == TOKEN
    assert parsed.expires_at is not None


def test_accepts_an_epoch_supplied_as_a_string():
    raw = json.dumps({"claudeAiOauth": {"accessToken": TOKEN, "expiresAt": str(epoch_ms(5))}})
    assert svc.parse_credentials(raw).expires_at is not None


def test_defaults_scopes_and_subscription_like_the_frontend():
    parsed = svc.parse_credentials(json.dumps({"accessToken": TOKEN}))
    assert parsed.scopes == ["user:inference"]
    assert parsed.subscription_type == "Claude account"
    assert parsed.expires_at is None


@pytest.mark.parametrize(
    "raw",
    [
        "",
        "not json at all",
        "[]",
        '"a string"',
        "null",
        json.dumps({"claudeAiOauth": {}}),
        json.dumps({"claudeAiOauth": {"accessToken": ""}}),
        json.dumps({"claudeAiOauth": {"accessToken": 12345}}),
        json.dumps({"refreshToken": "only-a-refresh-token"}),
    ],
    ids=[
        "empty",
        "not-json",
        "array-root",
        "string-root",
        "null-root",
        "no-token",
        "empty-token",
        "non-string-token",
        "refresh-only",
    ],
)
def test_rejects_anything_without_an_access_token(raw):
    with pytest.raises(svc.ClaudeCredentialsError) as exc:
        svc.parse_credentials(raw)
    assert str(exc.value) == svc.INVALID_CREDENTIAL_MESSAGE


def test_the_rejection_message_never_quotes_the_file():
    """A malformed credentials file is still full of token material — the 400
    detail must be a fixed string, not the decoder's echo of the content."""
    raw = json.dumps({"claudeAiOauth": {"refreshToken": TOKEN}})
    with pytest.raises(svc.ClaudeCredentialsError) as exc:
        svc.parse_credentials(raw)
    assert TOKEN not in str(exc.value)


# ------------------------------------------------------------------ expiry
@pytest.mark.parametrize(
    ("days", "expected"),
    [
        (None, STATUS_ACTIVE),
        (90, STATUS_ACTIVE),
        (3, STATUS_ACTIVE),
        (2, STATUS_EXPIRING),
        (0, STATUS_EXPIRING),
        (-1, STATUS_EXPIRED),
        (-90, STATUS_EXPIRED),
    ],
)
def test_the_derived_status_rule_matches_the_handoff(days, expected):
    assert svc.status_of(days) == expected


def test_days_left_is_none_without_an_expiry():
    assert svc.days_left(None) is None


def test_days_left_counts_whole_days_forward_and_backward():
    now = datetime(2026, 7, 29, 12, 0, tzinfo=timezone.utc)
    assert svc.days_left(now + timedelta(days=30), now) == 30
    assert svc.days_left(now - timedelta(days=5), now) == -5


def test_upload_derives_status_and_metadata_from_the_file(db_session, make_user):
    user = make_user("meta@emesoft.net")
    # No refresh token, so the expiry still drives the derived state — that is
    # the only case where `expiring` is meaningful (issue #70).
    row = svc.upsert_own(db_session, user.id, creds_file(days=1, refresh=False), "laptop")
    # Stored status stays `active`; "expiring" is a derived display state only.
    assert row.status == STATUS_ACTIVE
    assert svc.derived_status(row) == STATUS_EXPIRING
    assert row.subscription_type == "max"
    assert row.label == "laptop"


def test_an_expired_file_with_no_refresh_token_derives_expired(db_session, make_user):
    user = make_user("stale@emesoft.net")
    row = svc.upsert_own(db_session, user.id, creds_file(days=-3, refresh=False))
    assert row.has_refresh_token is False
    assert svc.derived_status(row) == STATUS_EXPIRED


def test_a_stored_expired_flag_wins_over_a_future_expiry(db_session, make_user):
    """An agent's real "not logged in" verdict beats the timestamp."""
    user = make_user("flagged@emesoft.net")
    row = svc.upsert_own(db_session, user.id, creds_file(days=90))
    assert svc.derived_status(row) == STATUS_ACTIVE
    assert svc.mark_expired(db_session, row) is True
    assert svc.derived_status(row) == STATUS_EXPIRED
    # Idempotent, and one-way: nothing here can declare a credential healthy.
    assert svc.mark_expired(db_session, row) is False


# ------------------------------------------------- refresh tokens (issue #63)
def test_an_elapsed_expiry_with_a_refresh_token_is_not_expired(db_session, make_user):
    """The bug: an access token lives hours, so a real `.credentials.json` is
    stale almost immediately — but the CLI renews it from the refresh token
    beside it. Every credential anyone uploaded went red within an afternoon."""
    user = make_user("realfile@emesoft.net")
    row = svc.upsert_own(db_session, user.id, creds_file(days=-3))

    assert row.has_refresh_token is True
    status = svc.derived_status(row)
    assert status != STATUS_EXPIRED
    assert status == STATUS_REFRESHABLE


@pytest.mark.parametrize("elapsed_days", [-0.125, -1, -400])
def test_the_refresh_rule_holds_however_long_ago_it_lapsed(
    db_session, make_user, elapsed_days
):
    """Including the -3h case, where `daysLeft` rounds to 0 and the old rule
    would have said `expiring` rather than either honest answer."""
    user = make_user(f"lapsed{abs(elapsed_days)}@emesoft.net")
    row = svc.upsert_own(db_session, user.id, creds_file(days=elapsed_days))
    assert svc.derived_status(row) == STATUS_REFRESHABLE


@pytest.mark.parametrize("elapsed_days", [-1, -400])
def test_without_a_refresh_token_an_elapsed_expiry_is_still_expired(
    db_session, make_user, elapsed_days
):
    user = make_user(f"dead{abs(elapsed_days)}@emesoft.net")
    row = svc.upsert_own(db_session, user.id, creds_file(days=elapsed_days, refresh=False))
    assert svc.derived_status(row) == STATUS_EXPIRED


def test_a_few_hours_past_expiry_with_no_refresh_token_stays_the_handoffs_answer(
    db_session, make_user
):
    """`status_of` is the handoff's rule and is left verbatim: it rounds, so
    three hours past expiry is `daysLeft == 0` and reads `expiring`. Recorded
    here so the boundary is a decision rather than an accident — issue #63
    changes only what happens when a refresh token IS present."""
    user = make_user("hours@emesoft.net")
    row = svc.upsert_own(db_session, user.id, creds_file(days=-0.125, refresh=False))
    assert svc.derived_status(row) == STATUS_EXPIRING


def test_a_refresh_token_silences_the_expiry_warning_entirely(db_session, make_user):
    """Issue #70. This asserted the opposite until now — that a credential
    expiring within two days still warns ``expiring`` even with a refresh token
    on file, so as not to "paper over the warning".

    That is wrong for this credential type. A Claude OAuth *access* token lives
    hours, so ``daysLeft <= 2`` is true from the moment of upload and stays
    true: every working credential rendered amber **Expiring** permanently. The
    warning was not protecting anyone — it was the resting state.

    With a refresh token on file the access token's expiry is not a health
    signal at all: ``active`` before it elapses, ``refreshable`` after, and the
    only route to ``expired`` is the CLI actually rejecting it.
    """
    user = make_user("future@emesoft.net")

    # Not yet elapsed — including 1 day out, which used to warn.
    for days in (90, 2, 1):
        assert (
            svc.derived_status(
                svc.upsert_own(db_session, user.id, creds_file(days=days))
            )
            == STATUS_ACTIVE
        ), f"{days}d out with a refresh token — nothing to warn about"

    # The invariant that actually matters, and the one that is boundary-safe:
    # with a refresh token the clock can never produce a state that asks the
    # user to do something. `days=0` straddles "now", so it may land either
    # side — both answers are fine, neither may be a warning.
    for days in (0, -1, -30):
        assert svc.derived_status(
            svc.upsert_own(db_session, user.id, creds_file(days=days))
        ) in (STATUS_ACTIVE, STATUS_REFRESHABLE), f"{days}d must not warn"


def test_without_a_refresh_token_the_expiry_still_warns(db_session, make_user):
    """The counterpart, and why the rule is conditional rather than deleted:
    expiry is a real signal when nothing can renew it. Then ``expiring`` means
    "act soon" and is worth showing."""
    user = make_user("norefresh@emesoft.net")
    assert (
        svc.derived_status(
            svc.upsert_own(db_session, user.id, creds_file(days=90, refresh=False))
        )
        == STATUS_ACTIVE
    )
    assert (
        svc.derived_status(
            svc.upsert_own(db_session, user.id, creds_file(days=1, refresh=False))
        )
        == STATUS_EXPIRING
    )


def test_the_cli_verdict_still_wins_over_a_refresh_token(db_session, make_user):
    """`_mark_credential_invalid` is the only signal that a credential truly does
    not work. A refresh token on file must not be able to argue with it."""
    user = make_user("rejected@emesoft.net")
    row = svc.upsert_own(db_session, user.id, creds_file(days=-3))
    assert svc.derived_status(row) == STATUS_REFRESHABLE

    from app.services import claude_cli

    claude_cli._mark_credential_invalid(db_session, user.id)
    db_session.refresh(row)

    assert row.status == STATUS_EXPIRED
    assert row.has_refresh_token is True  # still true — it just does not matter
    assert svc.derived_status(row) == STATUS_EXPIRED


def test_the_refresh_token_itself_is_never_stored_outside_the_blob(
    db_session, make_user
):
    user = make_user("nostore@emesoft.net")
    row = svc.upsert_own(db_session, user.id, creds_file(days=-3))
    db_session.refresh(row)

    refresh_token = "sk-ant-ort01-refresh"
    # It IS in the encrypted blob — otherwise the assertion below is vacuous.
    assert refresh_token in (crypto.decrypt(row.credentials) or "")
    # ...and nowhere else on the row, nor in anything the row hands out.
    for column in row.__table__.columns:
        if column.name == "credentials":
            continue
        assert refresh_token not in str(getattr(row, column.name))
    assert refresh_token not in json.dumps(svc.meta_for(row), default=str)
    assert refresh_token not in json.dumps(svc.status_for(db_session, user.id), default=str)


def test_the_null_flag_is_backfilled_lazily_exactly_once(db_session, make_user):
    """Rows predating the column carry NULL. The first read resolves it from
    the blob; nothing after that decrypts again."""
    user = make_user("legacy@emesoft.net")
    row = svc.upsert_own(db_session, user.id, creds_file(days=-3))

    # Rewind to the pre-migration state.
    row.has_refresh_token = None
    db_session.commit()
    assert svc.derived_status(row) == STATUS_EXPIRED  # NULL reads as "no refresh"

    decrypts = {"n": 0}
    real_decrypt = crypto.decrypt

    def counting(value):
        decrypts["n"] += 1
        return real_decrypt(value)

    import app.services.claude_credentials as module

    original = module.crypto.decrypt
    module.crypto.decrypt = counting
    try:
        assert svc.backfill_refresh_flag(db_session, row) is True
        assert decrypts["n"] == 1
        # Every later call short-circuits before touching crypto at all.
        assert svc.backfill_refresh_flag(db_session, row) is True
        assert svc.backfill_refresh_flag(db_session, row) is True
        assert decrypts["n"] == 1
    finally:
        module.crypto.decrypt = original

    db_session.refresh(row)
    assert row.has_refresh_token is True
    assert svc.derived_status(row) == STATUS_REFRESHABLE
    # The backfill wrote a boolean and nothing else.
    assert row.has_refresh_token is not None
    assert "sk-ant-ort01-refresh" not in str(row.label) + str(row.subscription_type)


def test_status_for_backfills_a_null_flag_before_deriving(db_session, make_user):
    """The read path the settings screen uses: a legacy row must not report
    `expired` even once."""
    user = make_user("legacyread@emesoft.net")
    row = svc.upsert_own(db_session, user.id, creds_file(days=-3))
    row.has_refresh_token = None
    db_session.commit()

    state = svc.status_for(db_session, user.id)
    assert state["own"]["status"] == STATUS_REFRESHABLE
    assert state["own"]["hasRefreshToken"] is True

    db_session.refresh(row)
    assert row.has_refresh_token is True  # settled on disk, not just in the response


def test_verify_reports_a_refreshable_credential_as_usable(db_session, make_user):
    user = make_user("verifyrefresh@emesoft.net")
    svc.upsert_own(db_session, user.id, creds_file(days=-3))

    outcome = svc.verify(db_session, user.id)
    assert outcome["result"] == "refreshable"
    assert outcome["ok"] is True
    # ...and it did NOT flag the row, unlike the genuinely-expired path.
    assert svc.get_own(db_session, user.id).status == STATUS_ACTIVE


# ------------------------------------------------------- encryption at rest
def test_the_blob_round_trips_through_the_enc_v1_envelope(db_session, make_user):
    user = make_user("crypt@emesoft.net")
    raw = creds_file()
    row = svc.upsert_own(db_session, user.id, raw)

    assert row.credentials.startswith("enc::v1:")
    assert crypto.is_encrypted(row.credentials)
    assert crypto.key_version_of(row.credentials) == "v1"
    assert TOKEN not in row.credentials
    assert crypto.decrypt(row.credentials) == raw


def test_the_stored_column_is_ciphertext_in_the_database(db_session, make_user):
    """Read the raw column back through SQL, not the ORM, so nothing can be
    decrypting it on the way out."""
    from sqlalchemy import text

    user = make_user("sql@emesoft.net")
    svc.upsert_own(db_session, user.id, creds_file())
    stored = db_session.execute(text("SELECT credentials FROM claude_credentials")).scalar()
    assert stored.startswith("enc::v1:")
    assert TOKEN not in stored


def test_encryption_does_not_use_the_jwt_secret(db_session, make_user, monkeypatch):
    """ADR 0005 — rotating the signing secret must not touch stored credentials."""
    import app.config as config_module

    user = make_user("adr5@emesoft.net")
    raw = creds_file()
    svc.upsert_own(db_session, user.id, raw)

    monkeypatch.setattr(config_module.settings, "jwt_secret", "a-completely-new-secret")
    # Rotating the signing secret leaves every stored credential readable.
    assert svc.resolve_material(db_session, user.id)["credentials"] == raw


def test_a_credential_encrypted_under_another_key_is_unreadable(
    db_session, make_user, monkeypatch
):
    import app.config as config_module

    user = make_user("rekey@emesoft.net")
    svc.upsert_own(db_session, user.id, creds_file())
    monkeypatch.setattr(config_module.settings, "encryption_key", "a-different-encryption-key")
    with pytest.raises(svc.ClaudeCredentialsError):
        svc.resolve_material(db_session, user.id)


# ------------------------------------------------------------- resolution
@pytest.fixture
def people(db_session, make_user):
    return {
        "alice": make_user("alice@emesoft.net"),
        "bob": make_user("bob@emesoft.net"),
        "admin": make_user("root@emesoft.net", role="admin"),
    }


def test_resolution_precedence_own_then_shared_then_none(db_session, people):
    alice = people["alice"]

    # none
    assert svc.resolve(db_session, alice.id) == (None, "none")
    assert svc.resolve_material(db_session, alice.id) is None

    # shared
    svc.upsert_shared(db_session, creds_file(OTHER_TOKEN), "workspace")
    row, source = svc.resolve(db_session, alice.id)
    assert source == "shared" and row.owner_id is None

    # own wins over shared
    svc.upsert_own(db_session, alice.id, creds_file(TOKEN))
    row, source = svc.resolve(db_session, alice.id)
    assert source == "own" and row.owner_id == alice.id
    assert TOKEN in svc.resolve_material(db_session, alice.id)["credentials"]


def test_prefer_shared_makes_an_own_credential_yield(db_session, people):
    alice = people["alice"]
    svc.upsert_shared(db_session, creds_file(OTHER_TOKEN))
    svc.upsert_own(db_session, alice.id, creds_file(TOKEN))

    svc.set_preferred_mode(db_session, alice.id, "shared")
    assert svc.resolve(db_session, alice.id)[1] == "shared"
    assert OTHER_TOKEN in svc.resolve_material(db_session, alice.id)["credentials"]

    # Non-destructive — flipping back needs no re-upload.
    svc.set_preferred_mode(db_session, alice.id, "own")
    assert svc.resolve(db_session, alice.id)[1] == "own"
    assert TOKEN in svc.resolve_material(db_session, alice.id)["credentials"]


def test_prefer_shared_is_ignored_when_there_is_no_shared_credential(db_session, people):
    """A user must never be left with nothing because of a stale preference."""
    alice = people["alice"]
    svc.upsert_shared(db_session, creds_file(OTHER_TOKEN))
    svc.upsert_own(db_session, alice.id, creds_file(TOKEN))
    svc.set_preferred_mode(db_session, alice.id, "shared")
    svc.delete_shared(db_session)

    assert svc.resolve(db_session, alice.id)[1] == "own"


def test_switching_to_shared_requires_a_shared_credential(db_session, people):
    alice = people["alice"]
    svc.upsert_own(db_session, alice.id, creds_file())
    with pytest.raises(svc.ClaudeCredentialsError, match="shared Claude account"):
        svc.set_preferred_mode(db_session, alice.id, "shared")


def test_switching_requires_an_own_credential_to_store_it_on(db_session, people):
    with pytest.raises(svc.ClaudeCredentialsError, match="no personal"):
        svc.set_preferred_mode(db_session, people["alice"].id, "shared")


def test_an_unknown_mode_is_rejected(db_session, people):
    svc.upsert_own(db_session, people["alice"].id, creds_file())
    with pytest.raises(svc.ClaudeCredentialsError, match="own"):
        svc.set_preferred_mode(db_session, people["alice"].id, "everyones")


def test_one_row_per_user_and_one_shared_row(db_session, people):
    alice = people["alice"]
    svc.upsert_own(db_session, alice.id, creds_file())
    svc.upsert_own(db_session, alice.id, creds_file(OTHER_TOKEN), "replaced")
    svc.upsert_shared(db_session, creds_file())
    svc.upsert_shared(db_session, creds_file(OTHER_TOKEN))

    assert db_session.query(ClaudeCredentials).count() == 2
    assert svc.get_own(db_session, alice.id).label == "replaced"
    assert OTHER_TOKEN in svc.resolve_material(db_session, alice.id)["credentials"]


def test_deleting_an_own_credential_falls_back_to_shared(db_session, people):
    alice = people["alice"]
    svc.upsert_shared(db_session, creds_file(OTHER_TOKEN))
    svc.upsert_own(db_session, alice.id, creds_file(TOKEN))
    assert svc.delete_own(db_session, alice.id) is True
    assert svc.resolve(db_session, alice.id)[1] == "shared"
    assert svc.delete_own(db_session, alice.id) is False


def test_one_users_credential_is_never_resolved_for_another(db_session, people):
    svc.upsert_own(db_session, people["alice"].id, creds_file(TOKEN))
    assert svc.get_own(db_session, people["bob"].id) is None
    assert svc.resolve(db_session, people["bob"].id) == (None, "none")
    assert svc.resolve_material(db_session, people["bob"].id) is None


# ------------------------------------------------------------ status_for
def test_status_for_never_carries_the_token(db_session, people):
    alice = people["alice"]
    svc.upsert_shared(db_session, creds_file(OTHER_TOKEN))
    svc.upsert_own(db_session, alice.id, creds_file(TOKEN), "laptop")

    payload = svc.status_for(db_session, alice.id)
    assert payload["hasOwn"] is True and payload["hasShared"] is True
    assert payload["mode"] == "own"
    blob = json.dumps(payload, default=str)
    assert TOKEN not in blob and OTHER_TOKEN not in blob
    assert "credentials" not in blob


def test_status_for_counts_the_users_falling_back_to_shared(db_session, people):
    svc.upsert_shared(db_session, creds_file())
    svc.upsert_own(db_session, people["alice"].id, creds_file())
    # alice has her own; bob and the admin fall back.
    assert svc.status_for(db_session, people["alice"].id)["shared"]["assignedUsers"] == 2


def test_status_for_reports_none_when_nothing_is_configured(db_session, people):
    payload = svc.status_for(db_session, people["alice"].id)
    assert payload == {
        "hasOwn": False,
        "hasShared": False,
        "mode": "none",
        "preferShared": False,
        "own": None,
        "shared": None,
    }


# -------------------------------------------------------- rotation write-back
def test_a_strictly_newer_token_is_captured(db_session, people):
    alice = people["alice"]
    svc.upsert_own(db_session, alice.id, creds_file(TOKEN, days=1))
    rotated = creds_file(OTHER_TOKEN, days=30)

    assert svc.persist_refreshed_from_raw(db_session, alice.id, rotated) is True
    assert svc.resolve_material(db_session, alice.id)["credentials"] == rotated


@pytest.mark.parametrize(
    "rotated",
    [
        "",
        "   ",
        json.dumps({"claudeAiOauth": {}}),  # logged out
        "garbage",
    ],
    ids=["empty", "blank", "logged-out", "malformed"],
)
def test_a_failed_refresh_never_clobbers_a_good_credential(db_session, people, rotated):
    alice = people["alice"]
    good = creds_file(TOKEN, days=30)
    svc.upsert_own(db_session, alice.id, good)

    assert svc.persist_refreshed_from_raw(db_session, alice.id, rotated) is False
    assert svc.resolve_material(db_session, alice.id)["credentials"] == good


def test_an_older_or_equal_token_is_not_captured(db_session, people):
    alice = people["alice"]
    good = creds_file(TOKEN, days=30)
    svc.upsert_own(db_session, alice.id, good)

    assert svc.persist_refreshed_from_raw(db_session, alice.id, creds_file(OTHER_TOKEN, days=1)) is False
    assert svc.resolve_material(db_session, alice.id)["credentials"] == good


def test_the_write_back_follows_the_same_precedence_as_resolve(db_session, people):
    """A rotation posted by a user running on the shared account updates the
    shared row, not a phantom personal one."""
    alice = people["alice"]
    svc.upsert_shared(db_session, creds_file(OTHER_TOKEN, days=1))
    rotated = creds_file("sk-ant-oat01-ROTATED", days=40)

    assert svc.persist_refreshed_from_raw(db_session, alice.id, rotated) is True
    assert svc.get_own(db_session, alice.id) is None
    assert crypto.decrypt(svc.get_shared(db_session).credentials) == rotated


def test_a_capture_clears_a_previously_expired_flag(db_session, people):
    alice = people["alice"]
    row = svc.upsert_own(db_session, alice.id, creds_file(TOKEN, days=1))
    svc.mark_expired(db_session, row)
    svc.persist_refreshed_from_raw(db_session, alice.id, creds_file(OTHER_TOKEN, days=30))
    assert svc.get_own(db_session, alice.id).status == STATUS_ACTIVE


def test_a_write_back_with_no_credential_at_all_is_a_no_op(db_session, people):
    assert svc.persist_refreshed_from_raw(db_session, people["alice"].id, creds_file()) is False


# ------------------------------------------------------------------ verify
def test_verify_reports_a_missing_credential(db_session, people):
    result = svc.verify(db_session, people["alice"].id)
    assert result["ok"] is False and result["result"] == "no_credential"


def test_verify_passes_a_healthy_credential(db_session, people):
    svc.upsert_own(db_session, people["alice"].id, creds_file(days=30))
    assert svc.verify(db_session, people["alice"].id)["result"] == "ok"


def test_verify_flags_and_records_an_expired_credential(db_session, people):
    alice = people["alice"]
    # No refresh token: the one case where an elapsed expiry really is death.
    svc.upsert_own(db_session, alice.id, creds_file(days=-1, refresh=False))
    assert svc.verify(db_session, alice.id)["result"] == "expired"
    assert svc.get_own(db_session, alice.id).status == STATUS_EXPIRED


def test_verify_reports_an_undecryptable_credential(db_session, people, monkeypatch):
    import app.config as config_module

    svc.upsert_own(db_session, people["alice"].id, creds_file())
    monkeypatch.setattr(config_module.settings, "encryption_key", "yet-another-key")
    assert svc.verify(db_session, people["alice"].id)["result"] == "undecryptable"


def test_verify_can_target_the_shared_account_explicitly(db_session, people):
    alice = people["alice"]
    svc.upsert_own(db_session, alice.id, creds_file(days=30))
    svc.upsert_shared(db_session, creds_file(OTHER_TOKEN, days=-5, refresh=False))

    assert svc.verify(db_session, alice.id, "own")["result"] == "ok"
    assert svc.verify(db_session, alice.id, "effective")["result"] == "ok"
    assert svc.verify(db_session, alice.id, "shared")["result"] == "expired"


def test_verify_never_returns_the_token(db_session, people):
    svc.upsert_own(db_session, people["alice"].id, creds_file())
    assert TOKEN not in json.dumps(svc.verify(db_session, people["alice"].id))
