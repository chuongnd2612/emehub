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


# ---------------------------------------------------------------- deletion
def _ticket(db, *, project_id, owner_id, external_id="SUR-1"):
    from app.models.ticket import Ticket

    row = Ticket(
        external_id=external_id,
        provider_kind="ado",
        project_id=project_id,
        title="A mirrored work item",
        owner_id=owner_id,
    )
    db.add(row)
    db.commit()
    return row


def test_delete_removes_the_project_and_it_stops_resolving(client, alice, auth_headers):
    headers = auth_headers("alice@emesoft.net", PASSWORD)
    client.post("/projects", json={"key": "doomed"}, headers=headers)
    assert client.get("/projects/doomed", headers=headers).status_code == 200

    assert client.delete("/projects/doomed", headers=headers).status_code == 204
    assert client.get("/projects/doomed", headers=headers).status_code == 404
    assert client.delete("/projects/doomed", headers=headers).status_code == 404


def test_delete_takes_the_config_and_knowledge_rows_with_it(
    client, db_session, alice, auth_headers
):
    from app.models.knowledge import ProjectKnowledge

    headers = auth_headers("alice@emesoft.net", PASSWORD)
    client.post("/projects", json={"key": "shop"}, headers=headers)
    _save_config(
        client,
        headers,
        "shop",
        baseUrl="https://shop.test",
        testAccounts=[{"role": "qa", "username": "qa@x", "password": PASSWORD}],
    )
    db_session.add(
        ProjectKnowledge(key="shop::web", project_key="shop", repo="web", owner_id=alice.id)
    )
    db_session.add(ProjectKnowledge(key="shop", project_key="shop", owner_id=alice.id))
    db_session.commit()

    # Non-vacuous: they exist before the delete.
    assert db_session.query(ProjectConfig).filter_by(key="shop").count() == 1
    assert db_session.query(ProjectKnowledge).filter_by(project_key="shop").count() == 2

    assert client.delete("/projects/shop", headers=headers).status_code == 204

    assert db_session.query(ProjectConfig).filter_by(key="shop").count() == 0
    assert db_session.query(ProjectKnowledge).filter_by(project_key="shop").count() == 0
    assert db_session.query(Project).filter_by(key="shop").count() == 0


def test_delete_never_touches_another_namespaces_same_key(
    client, db_session, alice, bob, admin, auth_headers
):
    """Alice deleting her own `shop` must leave Bob and the shared one standing."""
    from app.models.knowledge import ProjectKnowledge

    for owner in (alice.id, bob.id, None):
        _project(db_session, "shop", owner)
        db_session.add(ProjectConfig(key="shop", owner_id=owner))
        db_session.add(ProjectKnowledge(key="shop", project_key="shop", owner_id=owner))
    db_session.commit()

    headers = auth_headers("alice@emesoft.net", PASSWORD)
    assert client.delete("/projects/shop", headers=headers).status_code == 204

    assert {p.owner_id for p in db_session.query(Project).filter_by(key="shop")} == {
        bob.id,
        None,
    }
    assert {c.owner_id for c in db_session.query(ProjectConfig).filter_by(key="shop")} == {
        bob.id,
        None,
    }
    assert {
        k.owner_id for k in db_session.query(ProjectKnowledge).filter_by(project_key="shop")
    } == {bob.id, None}


def test_a_member_cannot_delete_another_members_project(
    client, db_session, alice, bob, auth_headers
):
    """404, never 403 - a 403 would confirm the other member has that project."""
    _project(db_session, "bob-only", bob.id)
    response = client.delete(
        "/projects/bob-only", headers=auth_headers("alice@emesoft.net", PASSWORD)
    )
    assert response.status_code == 404
    assert db_session.query(Project).filter_by(key="bob-only").count() == 1


def test_a_non_admin_cannot_delete_a_shared_project(client, db_session, alice, auth_headers):
    """Visible, so this one IS a 403 rather than a 404."""
    _project(db_session, "shared-app", None)
    response = client.delete(
        "/projects/shared-app", headers=auth_headers("alice@emesoft.net", PASSWORD)
    )
    assert response.status_code == 403
    assert db_session.query(Project).filter_by(key="shared-app").count() == 1


def test_an_admin_can_delete_a_shared_project(client, db_session, admin, auth_headers):
    _project(db_session, "shared-app", None)
    response = client.delete(
        "/projects/shared-app", headers=auth_headers("admin@emesoft.net", PASSWORD)
    )
    assert response.status_code == 204
    assert db_session.query(Project).filter_by(key="shared-app").count() == 0


def test_delete_refuses_while_work_items_still_reference_the_project(
    client, db_session, alice, auth_headers
):
    """Chosen behaviour: refuse. Do not orphan, and do not silently delete a
    mirror of real work items as a side effect of tidying the registry."""
    headers = auth_headers("alice@emesoft.net", PASSWORD)
    row = _project(db_session, "shop", alice.id)
    _ticket(db_session, project_id=row.id, owner_id=alice.id, external_id="SUR-1")
    _ticket(db_session, project_id=row.id, owner_id=alice.id, external_id="SUR-2")

    response = client.delete("/projects/shop", headers=headers)
    assert response.status_code == 409
    assert "2 work items" in response.json()["detail"]
    # Nothing was destroyed on the way to refusing.
    assert db_session.query(Project).filter_by(key="shop").count() == 1

    # Remove the blockers and it goes through.
    for external_id in ("SUR-1", "SUR-2"):
        assert client.delete(f"/tickets/{external_id}", headers=headers).status_code == 204
    assert client.delete("/projects/shop", headers=headers).status_code == 204


def test_another_members_tickets_do_not_block_a_delete(
    client, db_session, alice, bob, auth_headers
):
    """The count is namespace-scoped, like everything else in the slice."""
    alice_project = _project(db_session, "shop", alice.id)
    _ticket(db_session, project_id=alice_project.id, owner_id=bob.id, external_id="SUR-9")

    headers = auth_headers("alice@emesoft.net", PASSWORD)
    assert client.delete("/projects/shop", headers=headers).status_code == 204


def test_delete_removes_the_workspace_directories(
    client, db_session, alice, auth_headers, workspace_dir
):
    from app.services.workspace_scope import scoped_knowledge_dir, scoped_repos_dir

    headers = auth_headers("alice@emesoft.net", PASSWORD)
    client.post("/projects", json={"key": "shop"}, headers=headers)

    clone = scoped_repos_dir(alice.id) / "shop" / "web"
    clone.mkdir(parents=True)
    (clone / "README.md").write_text("cloned", encoding="utf-8")
    artefacts = scoped_knowledge_dir(alice.id) / "shop"
    artefacts.mkdir(parents=True)
    (artefacts / "knowledge.md").write_text("built", encoding="utf-8")

    assert client.delete("/projects/shop", headers=headers).status_code == 204

    assert not (scoped_repos_dir(alice.id) / "shop").exists()
    assert not artefacts.exists()
    # The scope directories themselves survive - only the project directory went.
    assert scoped_repos_dir(alice.id).is_dir()
    assert scoped_knowledge_dir(alice.id).is_dir()


def test_a_crafted_key_cannot_delete_outside_its_scope(
    client, db_session, alice, auth_headers, workspace_dir
):
    """`slug()` is the boundary; this asserts it holds for a key built to climb
    out of the scope directory."""
    from app.services import project_service
    from app.services.workspace_scope import scoped_repos_dir

    hostile = "../../../shared"
    row = _project(db_session, hostile, alice.id)

    victim = workspace_dir / "shared" / "repos" / "someone-elses"
    victim.mkdir(parents=True)
    (victim / "keep.txt").write_text("do not delete me", encoding="utf-8")
    # The scope the key is trying to climb out of, with a sibling to protect.
    scoped_repos_dir(alice.id).mkdir(parents=True, exist_ok=True)
    (scoped_repos_dir(alice.id) / "unrelated").mkdir()

    # Straight at the service, because the hostile key cannot survive a URL path.
    project_service.delete_project(db_session, row)
    db_session.commit()

    assert victim.is_dir()
    assert (victim / "keep.txt").read_text(encoding="utf-8") == "do not delete me"
    assert scoped_repos_dir(alice.id).is_dir()
    assert (scoped_repos_dir(alice.id) / "unrelated").is_dir()
    # It stayed inside the scope: the slugged name is what would have gone.
    assert not (scoped_repos_dir(alice.id) / "shared").exists()


def test_delete_is_hub_audience_only(client, db_session, alice, agent_headers):
    _project(db_session, "alice-app", alice.id)
    response = client.delete(
        "/projects/alice-app", headers=agent_headers("alice@emesoft.net")
    )
    assert response.status_code == 401
    assert db_session.query(Project).filter_by(key="alice-app").count() == 1


def test_delete_writes_an_audit_line_with_no_secrets(client, alice, auth_headers):
    headers = auth_headers("alice@emesoft.net", PASSWORD)
    client.post("/projects", json={"key": "shop"}, headers=headers)
    _save_config(
        client,
        headers,
        "shop",
        testAccounts=[{"role": "qa", "username": "qa@x", "password": PASSWORD}],
    )
    assert client.delete("/projects/shop", headers=headers).status_code == 204

    logs = client.get("/audit/events", headers=headers)
    assert logs.status_code == 200
    assert "Deleted project" in logs.text
    assert PASSWORD not in logs.text
