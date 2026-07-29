"""Project registry and configuration.

The properties that matter here are the ones a leak would be expensive in:

* per-owner isolation — a member sees own + shared, never another member's;
* ``(key, owner_id)`` uniqueness — the same key in two namespaces is legal, the
  same key twice in one is not;
* test-account passwords are encrypted at rest, returned **only** to the owning
  user, and never present in a list response;
* the router's posture — an agent token reads, a hub token writes.
"""

from __future__ import annotations

import pytest
from sqlalchemy.exc import IntegrityError

from app import crypto
from app.config import AUDIENCE_QAGENT
from app.models.project import Project
from app.models.project_config import ProjectConfig

PASSWORD = "password12345"


# ---------------------------------------------------------------- fixtures
@pytest.fixture
def agent_headers(login):
    """``Authorization`` carrying a **qagent**-audience token, as an agent holds."""

    def _headers(email: str, password: str = PASSWORD):
        body = login(email, password)
        return {"Authorization": f"Bearer {body['tokens'][AUDIENCE_QAGENT]}"}

    return _headers


@pytest.fixture
def alice(make_user):
    return make_user("alice@emesoft.net", PASSWORD)


@pytest.fixture
def bob(make_user):
    return make_user("bob@emesoft.net", PASSWORD)


@pytest.fixture
def admin(make_user):
    return make_user("admin@emesoft.net", PASSWORD, role="admin")


def _project(db, key, owner_id, name=""):
    row = Project(key=key, name=name or key, owner_id=owner_id)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


# ---------------------------------------------------------------- registry
def test_list_returns_own_plus_shared_never_another_members(
    client, db_session, alice, bob, auth_headers
):
    _project(db_session, "alice-app", alice.id)
    _project(db_session, "bob-app", bob.id)
    _project(db_session, "shared-app", None)

    keys = {
        p["key"]
        for p in client.get("/projects", headers=auth_headers("alice@emesoft.net", PASSWORD)).json()
    }
    assert keys == {"alice-app", "shared-app"}


def test_the_list_summary_reports_real_figures_and_no_secrets(
    client, db_session, alice, auth_headers
):
    """``summary`` exists so the list screen costs one request, not 3N+1.

    It must carry the card's real figures — and nothing credential-shaped,
    since a list response is the easiest thing to log wholesale.
    """
    row = _project(db_session, "surveyor", alice.id, name="Surveyor Web")
    db_session.add(
        ProjectConfig(
            key="surveyor",
            owner_id=alice.id,
            repos=[
                {
                    "name": "surveyor-web",
                    "repo_url": "https://git/x",
                    "default_branch": "main",
                    "default": True,
                },
                {"name": "surveyor-api"},
            ],
            test_accounts=[
                {
                    "role": "admin",
                    "username": "qa@x.io",
                    "password": crypto.encrypt("hunter2"),
                }
            ],
        )
    )
    db_session.commit()

    body = client.get(
        "/projects", headers=auth_headers("alice@emesoft.net", PASSWORD)
    ).json()
    listed = next(p for p in body if p["key"] == "surveyor")
    summary = listed["summary"]

    assert listed["id"] == row.id
    assert summary["repo"] == "surveyor-web"
    assert summary["branch"] == "main"
    assert summary["repoCount"] == 2
    assert summary["ticketCount"] == 0
    assert summary["knowledgeStatus"] == "not_indexed"

    # Nothing credential-shaped, at any depth.
    serialised = str(body).lower()
    assert "hunter2" not in serialised
    assert "password" not in serialised
    assert "testaccounts" not in serialised


def test_a_key_in_both_namespaces_resolves_to_the_owned_row(
    client, db_session, alice, auth_headers
):
    """own → shared precedence, in the list and in the detail read alike."""
    _project(db_session, "billing", None, name="Shared Billing")
    _project(db_session, "billing", alice.id, name="Alice Billing")

    headers = auth_headers("alice@emesoft.net", PASSWORD)
    listed = [p for p in client.get("/projects", headers=headers).json() if p["key"] == "billing"]
    assert len(listed) == 1
    assert listed[0]["name"] == "Alice Billing"
    assert listed[0]["shared"] is False
    assert client.get("/projects/billing", headers=headers).json()["name"] == "Alice Billing"


def test_another_members_project_is_a_404_not_a_403(client, db_session, alice, bob, auth_headers):
    _project(db_session, "alice-only", alice.id)
    response = client.get("/projects/alice-only", headers=auth_headers("bob@emesoft.net", PASSWORD))
    # 403 would confirm the project exists.
    assert response.status_code == 404


def test_the_same_key_is_unique_per_owner_and_legal_across_owners(db_session, alice, bob):
    _project(db_session, "shop", alice.id)
    _project(db_session, "shop", bob.id)  # different namespace — fine
    _project(db_session, "shop", None)  # shared — fine

    db_session.add(Project(key="shop", name="dup", owner_id=alice.id))
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_create_project_lands_in_the_callers_namespace(client, alice, auth_headers):
    headers = auth_headers("alice@emesoft.net", PASSWORD)
    body = client.post("/projects", json={"key": "new-app", "name": "New"}, headers=headers).json()
    assert body["key"] == "new-app"
    assert body["shared"] is False


def test_a_member_asking_for_a_shared_project_gets_their_own(client, alice, auth_headers):
    """``shared`` is admin-only; a member must not silently create a project
    everyone in the workspace reads."""
    headers = auth_headers("alice@emesoft.net", PASSWORD)
    body = client.post("/projects", json={"key": "sneaky", "shared": True}, headers=headers).json()
    assert body["shared"] is False


def test_an_admin_can_create_a_shared_project(client, admin, auth_headers):
    headers = auth_headers("admin@emesoft.net", PASSWORD)
    body = client.post("/projects", json={"key": "platform", "shared": True}, headers=headers).json()
    assert body["shared"] is True


def test_a_member_cannot_rename_a_shared_project(client, db_session, alice, auth_headers):
    _project(db_session, "shared-app", None)
    response = client.patch(
        "/projects/shared-app",
        json={"name": "hijacked"},
        headers=auth_headers("alice@emesoft.net", PASSWORD),
    )
    assert response.status_code == 403


# ---------------------------------------------------------------- posture
def test_an_agent_token_may_read_the_contract_endpoints(client, db_session, alice, agent_headers):
    _project(db_session, "alice-app", alice.id)
    headers = agent_headers("alice@emesoft.net")
    assert client.get("/projects", headers=headers).status_code == 200
    assert client.get("/projects/alice-app/config", headers=headers).status_code == 200


def test_an_agent_token_cannot_manage_projects(client, alice, agent_headers):
    """Reads and the knowledge write path are the agent's; hub management is not."""
    headers = agent_headers("alice@emesoft.net")
    assert client.post("/projects", json={"key": "x"}, headers=headers).status_code == 401
    assert client.put("/projects/x/config", json={}, headers=headers).status_code == 401


def test_projects_require_authentication(client):
    assert client.get("/projects").status_code == 401
    assert client.get("/projects/anything/config").status_code == 401


# ---------------------------------------------------------------- config
def _save_config(client, headers, key, **patch):
    response = client.put(f"/projects/{key}/config", json=patch, headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


def test_test_account_passwords_are_encrypted_at_rest(client, db_session, alice, auth_headers):
    headers = auth_headers("alice@emesoft.net", PASSWORD)
    client.post("/projects", json={"key": "shop"}, headers=headers)
    _save_config(
        client,
        headers,
        "shop",
        baseUrl="https://shop.example",
        testAccounts=[{"role": "admin", "username": "qa@example.com", "password": "s3cret!"}],
    )

    row = db_session.query(ProjectConfig).filter(ProjectConfig.key == "shop").one()
    stored = row.test_accounts[0]["password"]
    assert stored.startswith("enc::v1:")
    assert "s3cret!" not in stored
    assert crypto.decrypt(stored) == "s3cret!"


def test_the_owner_gets_the_plaintext_back(client, alice, auth_headers):
    headers = auth_headers("alice@emesoft.net", PASSWORD)
    client.post("/projects", json={"key": "shop"}, headers=headers)
    _save_config(
        client,
        headers,
        "shop",
        testAccounts=[{"role": "admin", "username": "qa@example.com", "password": "s3cret!"}],
    )

    account = client.get("/projects/shop/config", headers=headers).json()["testAccounts"][0]
    assert account["password"] == "s3cret!"
    assert account["hasPassword"] is True


def test_another_member_cannot_read_the_test_accounts(
    client, db_session, alice, bob, auth_headers
):
    """Alice's config is invisible to Bob entirely — the project 404s, so there
    is no response to leak a password into."""
    alice_headers = auth_headers("alice@emesoft.net", PASSWORD)
    client.post("/projects", json={"key": "shop"}, headers=alice_headers)
    _save_config(
        client,
        alice_headers,
        "shop",
        testAccounts=[{"role": "admin", "username": "qa@example.com", "password": "s3cret!"}],
    )

    response = client.get(
        "/projects/shop/config", headers=auth_headers("bob@emesoft.net", PASSWORD)
    )
    assert response.status_code == 404
    assert "s3cret!" not in response.text


def test_a_shared_config_never_reveals_its_passwords(
    client, db_session, admin, alice, auth_headers
):
    """A shared row is owned by nobody, so nobody is "the owning user" — not even
    the admin who wrote it. A secret everyone can read has left the hub."""
    admin_headers = auth_headers("admin@emesoft.net", PASSWORD)
    client.post("/projects", json={"key": "platform", "shared": True}, headers=admin_headers)
    _save_config(
        client,
        admin_headers,
        "platform",
        shared=True,
        testAccounts=[{"role": "qa", "username": "shared@example.com", "password": "team-pw"}],
    )

    for headers in (admin_headers, auth_headers("alice@emesoft.net", PASSWORD)):
        response = client.get("/projects/platform/config", headers=headers)
        assert response.status_code == 200, response.text
        account = response.json()["testAccounts"][0]
        assert account["hasPassword"] is True
        assert account["password"] is None
        assert "team-pw" not in response.text


def test_the_project_list_carries_no_account_material_at_all(client, alice, auth_headers):
    headers = auth_headers("alice@emesoft.net", PASSWORD)
    client.post("/projects", json={"key": "shop"}, headers=headers)
    _save_config(
        client,
        headers,
        "shop",
        testAccounts=[{"role": "admin", "username": "qa@example.com", "password": "s3cret!"}],
    )

    response = client.get("/projects", headers=headers)
    assert "s3cret!" not in response.text
    assert "testAccounts" not in response.text
    assert "hasPassword" not in response.text


def test_a_blank_password_preserves_the_stored_secret(client, db_session, alice, auth_headers):
    """Saving the masked form back must not wipe the credential."""
    headers = auth_headers("alice@emesoft.net", PASSWORD)
    client.post("/projects", json={"key": "shop"}, headers=headers)
    _save_config(
        client,
        headers,
        "shop",
        testAccounts=[{"role": "admin", "username": "qa@example.com", "password": "s3cret!"}],
    )
    _save_config(
        client,
        headers,
        "shop",
        testAccounts=[{"role": "admin", "username": "qa@example.com", "notes": "renamed"}],
    )

    account = client.get("/projects/shop/config", headers=headers).json()["testAccounts"][0]
    assert account["password"] == "s3cret!"
    assert account["notes"] == "renamed"


def test_an_undecryptable_password_is_reported_as_unavailable_not_as_ciphertext(
    client, db_session, alice, auth_headers
):
    headers = auth_headers("alice@emesoft.net", PASSWORD)
    client.post("/projects", json={"key": "shop"}, headers=headers)
    _save_config(
        client,
        headers,
        "shop",
        testAccounts=[{"role": "admin", "username": "qa@example.com", "password": "s3cret!"}],
    )
    row = db_session.query(ProjectConfig).filter(ProjectConfig.key == "shop").one()
    row.test_accounts = [{**row.test_accounts[0], "password": "enc::v9:garbage"}]
    db_session.commit()

    account = client.get("/projects/shop/config", headers=headers).json()["testAccounts"][0]
    assert account["password"] == ""
    assert "garbage" not in client.get("/projects/shop/config", headers=headers).text


def test_config_writes_are_scoped_to_the_callers_namespace(
    client, db_session, admin, alice, auth_headers
):
    """A member saving a config for a key that only exists shared must create
    their own row, never edit everyone's."""
    admin_headers = auth_headers("admin@emesoft.net", PASSWORD)
    client.post("/projects", json={"key": "platform", "shared": True}, headers=admin_headers)
    _save_config(client, admin_headers, "platform", shared=True, baseUrl="https://shared.example")

    alice_headers = auth_headers("alice@emesoft.net", PASSWORD)
    _save_config(client, alice_headers, "platform", baseUrl="https://alice.example")

    rows = {
        r.owner_id: r.base_url
        for r in db_session.query(ProjectConfig).filter(ProjectConfig.key == "platform").all()
    }
    assert rows == {None: "https://shared.example", alice.id: "https://alice.example"}


def test_config_uniqueness_is_per_owner(db_session, alice):
    db_session.add(ProjectConfig(key="shop", owner_id=alice.id))
    db_session.commit()
    db_session.add(ProjectConfig(key="shop", owner_id=None))
    db_session.commit()  # different namespace — fine
    db_session.add(ProjectConfig(key="shop", owner_id=alice.id))
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_repos_normalise_to_exactly_one_default(client, alice, auth_headers):
    headers = auth_headers("alice@emesoft.net", PASSWORD)
    client.post("/projects", json={"key": "shop"}, headers=headers)
    body = _save_config(
        client,
        headers,
        "shop",
        repos=[
            {"name": "web", "repoUrl": "https://git/web"},
            {"name": "api", "default": True},
            {"name": "jobs", "default": True},
        ],
    )
    assert [(r["name"], r["default"]) for r in body["repos"]] == [
        ("web", False),
        ("api", True),
        ("jobs", False),
    ]


def test_an_unconfigured_project_reads_as_a_blank_config_not_a_404(client, alice, auth_headers):
    """An agent mid-run must not be 404'd for a project nobody has configured yet."""
    headers = auth_headers("alice@emesoft.net", PASSWORD)
    client.post("/projects", json={"key": "bare"}, headers=headers)
    body = client.get("/projects/bare/config", headers=headers).json()
    assert body["baseUrl"] == ""
    assert body["testAccounts"] == []


def test_the_connection_bindings_round_trip_without_a_connections_table(
    client, alice, auth_headers
):
    """The two connection columns are plain integers until the connections slice
    adds the constraint — binding an id must not require that table to exist."""
    headers = auth_headers("alice@emesoft.net", PASSWORD)
    client.post("/projects", json={"key": "shop"}, headers=headers)
    body = _save_config(client, headers, "shop", workItemConnectionId=7, repositoryConnectionId=9)
    assert (body["workItemConnectionId"], body["repositoryConnectionId"]) == (7, 9)
    # Present-but-null clears a binding.
    cleared = _save_config(client, headers, "shop", workItemConnectionId=None)
    assert cleared["workItemConnectionId"] is None
    assert cleared["repositoryConnectionId"] == 9
