"""Workspace scoping — ``owner_id`` + the shared (NULL) namespace.

Exercised against ``audit_logs``, the one scoped table this slice ships. The
rule it proves is the one every later domain slice inherits: a user sees their
own rows plus the shared namespace, and never another user's.
"""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from app.models.audit import AuditLog
from app.services.ownership import (
    can_write_shared,
    check_owned_or_404,
    get_owned_or_404,
    owned,
    stamp_owner,
)


def _event(db, owner_id, action):
    row = AuditLog(category="auth", action=action, owner_id=owner_id)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


@pytest.fixture
def scenario(db_session, make_user):
    alice = make_user("alice@emesoft.net")
    bob = make_user("bob@emesoft.net")
    return {
        "alice": alice,
        "bob": bob,
        "alice_row": _event(db_session, alice.id, "alice-only"),
        "bob_row": _event(db_session, bob.id, "bob-only"),
        "shared_row": _event(db_session, None, "shared"),
    }


# ---------------------------------------------------------------- owned()
def test_owned_returns_own_rows_plus_shared(db_session, scenario):
    rows = owned(db_session.query(AuditLog), AuditLog, scenario["alice"]).all()
    assert {r.action for r in rows} == {"alice-only", "shared"}


def test_owned_never_returns_another_users_rows(db_session, scenario):
    rows = owned(db_session.query(AuditLog), AuditLog, scenario["bob"]).all()
    assert "alice-only" not in {r.action for r in rows}
    assert {r.action for r in rows} == {"bob-only", "shared"}


def test_owned_fails_closed_without_a_user(db_session, scenario):
    """Not QAgent's bridge behaviour: no user means *nothing*, not everything."""
    assert owned(db_session.query(AuditLog), AuditLog, None).all() == []


# ---------------------------------------------------------------- get_owned_or_404
def test_get_owned_or_404_allows_own_and_shared(db_session, scenario):
    alice = scenario["alice"]
    assert get_owned_or_404(db_session, AuditLog, scenario["alice_row"].id, alice).action == "alice-only"
    assert get_owned_or_404(db_session, AuditLog, scenario["shared_row"].id, alice).action == "shared"


def test_get_owned_or_404_hides_another_users_row_as_a_404(db_session, scenario):
    with pytest.raises(HTTPException) as exc:
        get_owned_or_404(db_session, AuditLog, scenario["bob_row"].id, scenario["alice"])
    # 404 rather than 403: a 403 would confirm the row exists.
    assert exc.value.status_code == 404


def test_get_owned_or_404_on_a_missing_row(db_session, scenario):
    with pytest.raises(HTTPException) as exc:
        get_owned_or_404(db_session, AuditLog, 999_999, scenario["alice"])
    assert exc.value.status_code == 404


def test_get_owned_or_404_without_a_user(db_session, scenario):
    with pytest.raises(HTTPException):
        get_owned_or_404(db_session, AuditLog, scenario["shared_row"].id, None)


# ---------------------------------------------------------------- check / stamp
def test_check_owned_or_404(db_session, scenario):
    check_owned_or_404(None, scenario["alice"])  # absence is the caller's business
    check_owned_or_404(scenario["shared_row"], scenario["alice"])
    with pytest.raises(HTTPException):
        check_owned_or_404(scenario["bob_row"], scenario["alice"])


def test_stamp_owner_sets_the_owner(db_session, scenario):
    row = AuditLog(category="auth", action="x")
    assert stamp_owner(row, scenario["alice"]).owner_id == scenario["alice"].id


def test_stamp_owner_with_no_user_leaves_the_row_shared(db_session):
    row = AuditLog(category="auth", action="x")
    assert stamp_owner(row, None).owner_id is None


def test_only_admins_may_write_the_shared_namespace(db_session, make_user):
    assert can_write_shared(make_user("m@emesoft.net")) is False
    assert can_write_shared(make_user("a@emesoft.net", role="admin")) is True
    assert can_write_shared(None) is False


# ---------------------------------------------------------------- through the API
def test_audit_read_is_scoped_to_the_caller(client, db_session, make_user, auth_headers):
    alice = make_user("scoped-a@emesoft.net", "password12345")
    bob = make_user("scoped-b@emesoft.net", "password12345")
    _event(db_session, alice.id, "alice-private")
    _event(db_session, bob.id, "bob-private")
    _event(db_session, None, "everyone")

    headers = auth_headers("scoped-a@emesoft.net", "password12345")
    actions = {e["action"] for e in client.get("/audit/events", headers=headers).json()}
    assert "alice-private" in actions
    assert "everyone" in actions
    assert "bob-private" not in actions
