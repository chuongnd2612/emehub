"""Admin user management, and the last-active-admin lockout guard.

The guard exists because there is no back door: with no boot-time secret
generation and no fail-open path, a workspace with zero active admins is a
workspace nobody can administer again.
"""

from __future__ import annotations


def test_member_cannot_reach_admin_endpoints(client, make_user, auth_headers):
    make_user("plain@emesoft.net", "password12345")
    headers = auth_headers("plain@emesoft.net", "password12345")

    assert client.get("/auth/users", headers=headers).status_code == 403
    assert (
        client.post(
            "/auth/users",
            json={"email": "x@emesoft.net", "password": "password12345"},
            headers=headers,
        ).status_code
        == 403
    )


def test_admin_lists_creates_and_updates_users(client, make_user, auth_headers):
    make_user("root@emesoft.net", "password12345", role="admin")
    headers = auth_headers("root@emesoft.net", "password12345")

    created = client.post(
        "/auth/users",
        json={
            "email": "New.Person@Emesoft.net",
            "firstName": "New",
            "lastName": "Person",
            "role": "member",
            "password": "password12345",
        },
        headers=headers,
    )
    assert created.status_code == 201, created.text
    assert created.json()["email"] == "new.person@emesoft.net"  # lowercased
    assert "passwordHash" not in created.text

    duplicate = client.post(
        "/auth/users",
        json={"email": "new.person@emesoft.net", "password": "password12345"},
        headers=headers,
    )
    assert duplicate.status_code == 409

    rows = client.get("/auth/users", headers=headers).json()
    assert {r["email"] for r in rows} == {"root@emesoft.net", "new.person@emesoft.net"}

    new_id = created.json()["id"]
    promoted = client.patch(
        f"/auth/users/{new_id}", json={"role": "admin"}, headers=headers
    )
    assert promoted.status_code == 200 and promoted.json()["role"] == "admin"


def test_invite_creates_a_passwordless_user_with_a_reset_token(
    client, make_user, auth_headers
):
    make_user("inviter@emesoft.net", "password12345", role="admin")
    headers = auth_headers("inviter@emesoft.net", "password12345")

    response = client.post(
        "/auth/users/invite",
        json={"email": "guest@emesoft.net", "role": "member"},
        headers=headers,
    )
    assert response.status_code == 201, response.text
    token = response.json()["resetToken"]
    assert token

    # The invitee cannot log in until they redeem the token.
    assert (
        client.post(
            "/auth/login", json={"email": "guest@emesoft.net", "password": ""}
        ).status_code
        == 401
    )
    assert (
        client.post("/auth/reset", json={"token": token, "password": "chosenpass1"}).status_code
        == 200
    )
    assert (
        client.post(
            "/auth/login", json={"email": "guest@emesoft.net", "password": "chosenpass1"}
        ).status_code
        == 200
    )


def test_invalid_role_is_rejected(client, make_user, auth_headers):
    make_user("roles@emesoft.net", "password12345", role="admin")
    headers = auth_headers("roles@emesoft.net", "password12345")
    response = client.post(
        "/auth/users",
        json={"email": "x@emesoft.net", "password": "password12345", "role": "superuser"},
        headers=headers,
    )
    assert response.status_code == 400


# ---------------------------------------------------------------- lockout guard
def test_last_admin_cannot_demote_themselves(client, make_user, auth_headers):
    admin = make_user("only@emesoft.net", "password12345", role="admin")
    headers = auth_headers("only@emesoft.net", "password12345")

    response = client.patch(
        f"/auth/users/{admin.id}", json={"role": "member"}, headers=headers
    )
    assert response.status_code == 400
    assert "admin" in response.json()["detail"].lower()
    assert client.get("/auth/users", headers=headers).status_code == 200


def test_last_admin_cannot_deactivate_themselves(client, make_user, auth_headers):
    admin = make_user("solo@emesoft.net", "password12345", role="admin")
    headers = auth_headers("solo@emesoft.net", "password12345")

    response = client.patch(
        f"/auth/users/{admin.id}", json={"isActive": False}, headers=headers
    )
    assert response.status_code == 400


def test_last_admin_cannot_be_deleted(client, make_user, auth_headers):
    admin = make_user("final@emesoft.net", "password12345", role="admin")
    headers = auth_headers("final@emesoft.net", "password12345")

    assert client.delete(f"/auth/users/{admin.id}", headers=headers).status_code == 400
    assert client.delete("/auth/me", headers=headers).status_code == 400


def test_an_admin_can_step_down_once_another_admin_exists(client, make_user, auth_headers):
    first = make_user("a1@emesoft.net", "password12345", role="admin")
    make_user("a2@emesoft.net", "password12345", role="admin")
    headers = auth_headers("a1@emesoft.net", "password12345")

    response = client.patch(f"/auth/users/{first.id}", json={"role": "member"}, headers=headers)
    assert response.status_code == 200
    assert response.json()["role"] == "member"


def test_an_inactive_admin_does_not_count_towards_the_guard(client, make_user, auth_headers):
    active = make_user("live@emesoft.net", "password12345", role="admin")
    make_user("dormant@emesoft.net", "password12345", role="admin", active=False)
    headers = auth_headers("live@emesoft.net", "password12345")

    response = client.patch(f"/auth/users/{active.id}", json={"role": "member"}, headers=headers)
    assert response.status_code == 400


def test_deleting_a_user_removes_their_sessions(client, make_user, auth_headers, db_session):
    from app.models.session import Session as AuthSession

    make_user("admin2@emesoft.net", "password12345", role="admin")
    victim = make_user("temp@emesoft.net", "password12345")
    admin_headers = auth_headers("admin2@emesoft.net", "password12345")
    auth_headers("temp@emesoft.net", "password12345")
    assert db_session.query(AuthSession).filter_by(user_id=victim.id).count() == 1

    assert client.delete(f"/auth/users/{victim.id}", headers=admin_headers).status_code == 200
    assert db_session.query(AuthSession).filter_by(user_id=victim.id).count() == 0
