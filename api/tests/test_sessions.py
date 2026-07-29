"""Sessions: listing, revocation, and revocation taking effect immediately.

Revoking a session must kill the access token that carries its ``sid`` right
away at the hub — not fifteen minutes later when the token expires. (Agents
validate locally and therefore do have that window; INTEGRATION.md §2 accepts
it. The hub does not have to.)
"""

from __future__ import annotations


def test_list_sessions_marks_the_current_one(client, make_user, auth_headers):
    make_user("sess@emesoft.net", "password12345")
    headers = auth_headers("sess@emesoft.net", "password12345")

    rows = client.get("/auth/sessions", headers=headers).json()
    assert len(rows) == 1
    assert rows[0]["current"] is True
    # A session row never carries the refresh token, hashed or otherwise.
    assert "refreshTokenHash" not in rows[0]


def test_revoking_the_current_session_invalidates_its_access_token(
    client, make_user, auth_headers
):
    make_user("kill@emesoft.net", "password12345")
    headers = auth_headers("kill@emesoft.net", "password12345")
    sid = client.get("/auth/sessions", headers=headers).json()[0]["id"]

    assert client.delete(f"/auth/sessions/{sid}", headers=headers).status_code == 200
    assert client.get("/auth/me", headers=headers).status_code == 401
    assert client.get("/me", headers=headers).status_code == 401


def test_logout_revokes_the_session(client, make_user, auth_headers):
    make_user("bye@emesoft.net", "password12345")
    headers = auth_headers("bye@emesoft.net", "password12345")

    assert client.post("/auth/logout", headers=headers).status_code == 200
    assert client.get("/auth/me", headers=headers).status_code == 401


def test_a_user_cannot_revoke_someone_elses_session(client, make_user, auth_headers):
    make_user("owner@emesoft.net", "password12345")
    make_user("other@emesoft.net", "password12345")
    owner_headers = auth_headers("owner@emesoft.net", "password12345")
    owner_sid = client.get("/auth/sessions", headers=owner_headers).json()[0]["id"]

    other_headers = auth_headers("other@emesoft.net", "password12345")
    response = client.delete(f"/auth/sessions/{owner_sid}", headers=other_headers)
    assert response.status_code == 404  # 404, not 403 — do not confirm it exists
    assert client.get("/auth/me", headers=owner_headers).status_code == 200


def test_revoke_others_keeps_the_calling_session(client, make_user, auth_headers):
    make_user("many@emesoft.net", "password12345")
    first = auth_headers("many@emesoft.net", "password12345")
    second = auth_headers("many@emesoft.net", "password12345")
    assert len(client.get("/auth/sessions", headers=second).json()) == 2

    assert client.post("/auth/sessions/revoke-others", headers=second).status_code == 200
    rows = client.get("/auth/sessions", headers=second).json()
    assert len(rows) == 1 and rows[0]["current"] is True
    assert client.get("/auth/me", headers=first).status_code == 401


def test_an_expired_session_stops_working(client, make_user, auth_headers, db_session):
    from datetime import timedelta

    from app.db import utcnow
    from app.models.session import Session as AuthSession

    make_user("expired@emesoft.net", "password12345")
    headers = auth_headers("expired@emesoft.net", "password12345")
    row = db_session.query(AuthSession).one()
    row.expires_at = utcnow() - timedelta(seconds=1)
    db_session.add(row)
    db_session.commit()

    assert client.get("/auth/me", headers=headers).status_code == 401
    assert client.get("/auth/sessions", headers=headers).status_code == 401


def test_deactivating_a_user_kills_their_sessions(client, make_user, auth_headers):
    make_user("boss@emesoft.net", "password12345", role="admin")
    victim = make_user("victim@emesoft.net", "password12345")
    admin_headers = auth_headers("boss@emesoft.net", "password12345")
    victim_headers = auth_headers("victim@emesoft.net", "password12345")
    assert client.get("/auth/me", headers=victim_headers).status_code == 200

    patched = client.patch(
        f"/auth/users/{victim.id}", json={"isActive": False}, headers=admin_headers
    )
    assert patched.status_code == 200
    assert client.get("/auth/me", headers=victim_headers).status_code == 401
