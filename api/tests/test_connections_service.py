"""Capability routing, visibility and adapter construction.

``connection_service`` is what the tickets and projects slices import, so these
tests pin the routing rules rather than the HTTP surface: which connection a
ticket's work goes through, which one a project's code goes through, and who can
see what.
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from app import crypto
from app.models.provider_connection import ProviderConnection
from app.services import connection_service
from app.services.adapters.base import ProviderError

PAT = "pat-for-routing-tests"


@dataclass
class FakeTicket:
    """Satisfies ``connection_service.TicketLike`` without the tickets slice."""

    connection_id: int | None = None
    provider_kind: str = "azure_devops"
    owner_id: int | None = None


def make_connection(db, *, kind="azure_devops", owner_id=None, capabilities=None, pat=PAT):
    conn = ProviderConnection(
        kind=kind,
        label=f"{kind}-{owner_id}",
        base_url="https://dev.azure.com/emesoft",
        config={"project": "Surveyor"},
        pat_encrypted=crypto.encrypt(pat) if pat else None,
        capabilities=capabilities
        if capabilities is not None
        else connection_service.default_capabilities(kind),
        owner_id=owner_id,
    )
    db.add(conn)
    db.commit()
    db.refresh(conn)
    return conn


# ------------------------------------------------------------------ visibility
def test_a_viewer_sees_their_own_connections_plus_the_shared_ones(db_session, make_user):
    alice = make_user("alice@emesoft.net")
    bob = make_user("bob@emesoft.net")
    mine = make_connection(db_session, owner_id=alice.id)
    theirs = make_connection(db_session, owner_id=bob.id)
    shared = make_connection(db_session, owner_id=None)

    ids = [c.id for c in connection_service.list_connections(db_session, alice.id)]
    assert ids == [mine.id, shared.id]
    assert theirs.id not in ids

    assert connection_service.get_connection(db_session, theirs.id, alice.id) is None
    assert connection_service.get_connection(db_session, shared.id, alice.id) is not None


def test_no_viewer_means_the_shared_namespace_only(db_session, make_user):
    """Not QAgent's "no filtering" bridge: the hub never has a see-everything mode."""
    alice = make_user("alice@emesoft.net")
    private = make_connection(db_session, owner_id=alice.id)
    shared = make_connection(db_session, owner_id=None)

    ids = [c.id for c in connection_service.list_connections(db_session, None)]
    assert ids == [shared.id]
    assert private.id not in ids


# ---------------------------------------------------------------- capabilities
def test_connections_with_capability_splits_by_what_each_one_supplies(db_session, make_user):
    user = make_user()
    ado = make_connection(db_session, kind="azure_devops", owner_id=user.id)
    jira = make_connection(db_session, kind="jira", owner_id=user.id)
    repos_only = make_connection(
        db_session, kind="github", owner_id=user.id, capabilities=["repository"]
    )

    work_item = connection_service.connections_with_capability(db_session, "work_item", user.id)
    repository = connection_service.connections_with_capability(db_session, "repository", user.id)

    # Azure DevOps appears in both — that is the point of the capability model.
    assert [c.id for c in work_item] == [ado.id, jira.id]
    assert [c.id for c in repository] == [ado.id, repos_only.id]


def test_normalize_capabilities_rejects_what_the_adapter_cannot_do():
    assert connection_service.normalize_capabilities("github", None) == [
        "work_item",
        "repository",
    ]
    # Canonical order, not the caller's.
    assert connection_service.normalize_capabilities(
        "azure_devops", ["repository", "work_item"]
    ) == ["work_item", "repository"]

    with pytest.raises(ValueError, match="cannot supply"):
        connection_service.normalize_capabilities("jira", ["repository"])
    with pytest.raises(ValueError, match="Unknown capability"):
        connection_service.normalize_capabilities("github", ["deployments"])
    with pytest.raises(ValueError, match="at least one"):
        connection_service.normalize_capabilities("github", [])
    with pytest.raises(ValueError, match="Unknown provider kind"):
        connection_service.normalize_capabilities("gitlab", None)


def test_supported_capabilities_and_the_adapter_registry_agree():
    """A kind in the model with no adapter, or the reverse, is a wiring bug."""
    from app.models.provider_connection import PROVIDER_KINDS
    from app.services.adapters import registered_kinds

    assert set(PROVIDER_KINDS) == set(registered_kinds())


# ------------------------------------------------------------ work-item routing
def test_a_ticket_routes_through_its_stamped_connection(db_session, make_user):
    user = make_user()
    stamped = make_connection(db_session, owner_id=user.id)
    make_connection(db_session, owner_id=user.id)

    ticket = FakeTicket(connection_id=stamped.id, owner_id=user.id)
    assert connection_service.resolve_work_item_for_ticket(db_session, ticket).id == stamped.id


def test_an_unstamped_ticket_falls_back_to_the_first_of_its_kind(db_session, make_user):
    user = make_user()
    first = make_connection(db_session, kind="jira", owner_id=user.id)
    make_connection(db_session, kind="jira", owner_id=user.id)

    ticket = FakeTicket(connection_id=None, provider_kind="jira", owner_id=user.id)
    assert connection_service.resolve_work_item_for_ticket(db_session, ticket).id == first.id


def test_a_ticket_never_routes_through_another_members_connection(db_session, make_user):
    alice = make_user("alice@emesoft.net")
    bob = make_user("bob@emesoft.net")
    bobs = make_connection(db_session, owner_id=bob.id)

    # Alice's ticket, misbound to Bob's connection: refused, not honoured.
    ticket = FakeTicket(connection_id=bobs.id, owner_id=alice.id)
    with pytest.raises(ProviderError, match="No work-item connection"):
        connection_service.resolve_work_item_for_ticket(db_session, ticket)


def test_a_repository_only_connection_is_not_a_work_item_connection(db_session, make_user):
    user = make_user()
    repos_only = make_connection(
        db_session, kind="github", owner_id=user.id, capabilities=["repository"]
    )
    ticket = FakeTicket(
        connection_id=repos_only.id, provider_kind="github", owner_id=user.id
    )
    with pytest.raises(ProviderError):
        connection_service.resolve_work_item_for_ticket(db_session, ticket)


# ----------------------------------------------------------- repository routing
def test_a_project_routes_through_its_bound_repository_connection(db_session, make_user):
    user = make_user()
    make_connection(db_session, kind="azure_devops", owner_id=user.id)
    bound = make_connection(db_session, kind="github", owner_id=user.id)

    resolved = connection_service.resolve_repository_for_project(
        db_session, viewer_id=user.id, bound_connection_id=bound.id
    )
    assert resolved.id == bound.id


def test_an_unbound_project_falls_back_to_the_first_repository_connection(
    db_session, make_user
):
    user = make_user()
    # Jira first, and it can never serve repositories.
    make_connection(db_session, kind="jira", owner_id=user.id)
    ado = make_connection(db_session, kind="azure_devops", owner_id=user.id)

    resolved = connection_service.resolve_repository_for_project(
        db_session, viewer_id=user.id
    )
    assert resolved.id == ado.id


def test_no_repository_connection_at_all_is_an_error(db_session, make_user):
    user = make_user()
    make_connection(db_session, kind="jira", owner_id=user.id)
    with pytest.raises(ProviderError, match="No repository connection"):
        connection_service.resolve_repository_for_project(db_session, viewer_id=user.id)


# --------------------------------------------------------------------- adapters
def test_adapter_for_decrypts_the_pat_exactly_once_and_hands_it_over(db_session, make_user):
    user = make_user()
    conn = make_connection(db_session, owner_id=user.id, pat="round-trip-me")
    adapter = connection_service.adapter_for(conn)

    assert adapter.kind == "azure_devops"
    assert adapter.pat == "round-trip-me"
    # The stored column stays encrypted; nothing wrote the plaintext back.
    assert conn.pat_encrypted.startswith("enc::v1:")


def test_adapter_for_flattens_base_url_for_either_provider_spelling(db_session, make_user):
    user = make_user()
    conn = make_connection(db_session, owner_id=user.id)
    config = connection_service.adapter_config(conn)
    assert config["baseUrl"] == config["orgUrl"] == "https://dev.azure.com/emesoft"
    assert config["project"] == "Surveyor"


def test_an_undecryptable_pat_is_an_error_not_an_empty_credential(db_session, make_user):
    """A key rotation that lost the old key must look like "unavailable", never
    like "no PAT configured" — the second silently downgrades to anonymous."""
    user = make_user()
    conn = make_connection(db_session, owner_id=user.id)
    conn.pat_encrypted = "enc::v1:not-a-valid-fernet-token"
    db_session.commit()

    with pytest.raises(ProviderError, match="cannot be decrypted"):
        connection_service.adapter_for(conn)
