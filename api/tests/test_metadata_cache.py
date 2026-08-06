"""Cached provider metadata: fresh, refreshed, and stale-but-usable.

The third answer is the one worth testing hardest. A filter panel whose metadata
refresh failed must stay **usable** — the values from an hour ago are almost
certainly still right, and offering them beats an empty picker that silently builds
a query matching nothing. It has to say so, though; a failed load is never rendered
as "no data".
"""

from __future__ import annotations

from datetime import timedelta

import pytest

from app.db import utcnow
from app.models.metadata_cache import ProviderMetadataCache
from app.services import metadata_cache

PASSWORD = "password12345"

PAYLOAD = {
    "work_item_types": [{"name": "Bug", "states": ["Active", "Closed"]}],
    "area_paths": [{"id": "1", "name": "Data", "path": "Surency\\Data", "depth": 0}],
    "states": ["Active", "Closed"],
    "members": [{"display_name": "Duna", "unique_name": "duna@emesoft.net"}],
    "tags": ["backend"],
}


class Loader:
    """A metadata read that counts its calls and can be made to fail."""

    def __init__(self, payload=None, fails: bool = False) -> None:
        self.payload = payload if payload is not None else PAYLOAD
        self.fails = fails
        self.calls = 0

    def __call__(self):
        self.calls += 1
        if self.fails:
            raise RuntimeError("Azure DevOps did not answer")
        return self.payload


@pytest.fixture
def connection(db_session, make_user):
    from app.models.provider_connection import ProviderConnection

    user = make_user("meta@emesoft.net", PASSWORD)
    conn = ProviderConnection(
        kind="azure_devops",
        label="ADO — Surency",
        config={"orgUrl": "https://dev.azure.com/x", "project": "Surency"},
        capabilities=["work_item"],
        owner_id=user.id,
    )
    db_session.add(conn)
    db_session.commit()
    db_session.refresh(conn)
    return conn


def age(db_session, connection, minutes: int) -> None:
    """Backdate the cached read, so the TTL is genuinely exercised."""
    row = db_session.get(ProviderMetadataCache, connection.id)
    row.fetched_at = utcnow() - timedelta(minutes=minutes)
    db_session.add(row)
    db_session.commit()


# ─────────────────────────────────────────────────────────── the three answers
def test_a_first_read_hits_the_provider_and_is_stored(db_session, connection):
    load = Loader()
    result = metadata_cache.read(db_session, connection, load)

    assert load.calls == 1
    assert result.payload["tags"] == ["backend"]
    assert result.stale is False
    assert db_session.get(ProviderMetadataCache, connection.id) is not None


def test_a_second_read_inside_the_ttl_does_not_touch_the_provider(db_session, connection):
    """The whole reason the cache exists: every read spends the PAT."""
    load = Loader()
    metadata_cache.read(db_session, connection, load)
    result = metadata_cache.read(db_session, connection, load)

    assert load.calls == 1
    assert result.payload["tags"] == ["backend"]
    assert result.stale is False


def test_an_expired_entry_is_read_again(db_session, connection):
    load = Loader()
    metadata_cache.read(db_session, connection, load)
    age(db_session, connection, minutes=61)

    load.payload = {**PAYLOAD, "tags": ["backend", "urgent"]}
    result = metadata_cache.read(db_session, connection, load)

    assert load.calls == 2
    assert result.payload["tags"] == ["backend", "urgent"]
    assert result.stale is False


def test_refresh_forces_a_read_inside_the_ttl(db_session, connection):
    load = Loader()
    metadata_cache.read(db_session, connection, load)
    metadata_cache.read(db_session, connection, load, refresh=True)
    assert load.calls == 2


def test_a_failed_refresh_serves_the_cached_payload_and_says_why(db_session, connection):
    """Stale-but-usable. An empty picker silently builds a query matching
    nothing, which is worse than slightly old values that admit their age."""
    good = Loader()
    metadata_cache.read(db_session, connection, good)
    age(db_session, connection, minutes=61)

    result = metadata_cache.read(db_session, connection, Loader(fails=True))

    assert result.payload["tags"] == ["backend"], "the last good payload must survive"
    assert result.stale is True
    assert "did not answer" in result.message


def test_a_failed_refresh_does_not_advance_the_age(db_session, connection):
    """`fetched_at` is when the provider was really read. A failed refresh
    touching it would make a stale payload claim to be fresh."""
    metadata_cache.read(db_session, connection, Loader())
    age(db_session, connection, minutes=61)
    before = db_session.get(ProviderMetadataCache, connection.id).fetched_at

    result = metadata_cache.read(db_session, connection, Loader(fails=True))

    assert result.fetched_at == before
    assert db_session.get(ProviderMetadataCache, connection.id).fetched_at == before


def test_a_first_read_that_fails_raises_rather_than_faking_an_empty_payload(
    db_session, connection
):
    """Nothing cached to fall back on, so there is no honest answer but the error."""
    with pytest.raises(RuntimeError):
        metadata_cache.read(db_session, connection, Loader(fails=True))
    assert db_session.get(ProviderMetadataCache, connection.id) is None


# ───────────────────────────────────────────────────────────────── clearing
def test_clearing_drops_the_entry_and_the_next_read_refills_it(db_session, connection):
    load = Loader()
    metadata_cache.read(db_session, connection, load)

    assert metadata_cache.clear(db_session, connection.id) is True
    assert db_session.get(ProviderMetadataCache, connection.id) is None

    metadata_cache.read(db_session, connection, load)
    assert load.calls == 2


def test_clearing_nothing_is_not_an_error(db_session, connection):
    assert metadata_cache.clear(db_session, connection.id) is False


# ───────────────────────────────────────────────────────────── over HTTP
def test_the_endpoint_reports_the_age_and_the_staleness(client, make_user, auth_headers, monkeypatch):
    """What the panel prints — "fields read 4 minutes ago" — has to come from a
    real timestamp, not from the moment of the request."""
    from app.models.provider_connection import ProviderConnection
    from app.routers import connections as router

    user = make_user("meta-http@emesoft.net", PASSWORD)
    headers = auth_headers("meta-http@emesoft.net", PASSWORD)

    created = client.post(
        "/connections",
        json={
            "kind": "azure_devops",
            "label": "ADO",
            "config": {"orgUrl": "https://dev.azure.com/x", "project": "Surency"},
            "capabilities": ["work_item"],
            "pat": "secret",
        },
        headers=headers,
    )
    assert created.status_code == 201, created.text
    connection_id = created.json()["id"]

    class FakeAdapter:
        calls = 0

        def list_work_item_metadata(self):
            FakeAdapter.calls += 1
            return PAYLOAD

    monkeypatch.setattr(router, "_adapter", lambda conn: FakeAdapter())

    first = client.get(f"/connections/{connection_id}/work-item-metadata", headers=headers)
    assert first.status_code == 200, first.text
    body = first.json()
    assert body["fetchedAt"]
    assert body["stale"] is False
    assert body["workItemTypes"] == [{"name": "Bug", "states": ["Active", "Closed"]}]
    assert body["members"] == [{"displayName": "Duna", "uniqueName": "duna@emesoft.net"}]

    # Served from the cache — the provider is not touched again.
    client.get(f"/connections/{connection_id}/work-item-metadata", headers=headers)
    assert FakeAdapter.calls == 1

    # …until asked.
    client.get(
        f"/connections/{connection_id}/work-item-metadata?refresh=true", headers=headers
    )
    assert FakeAdapter.calls == 2

    # And clearing empties it.
    cleared = client.delete(f"/connections/{connection_id}/metadata/cache", headers=headers)
    assert cleared.status_code == 200
    client.get(f"/connections/{connection_id}/work-item-metadata", headers=headers)
    assert FakeAdapter.calls == 3


def test_the_metadata_routes_stay_hub_only(client, make_user, login):
    """They spend the PAT, so an agent token must not reach them until the
    deferred connections proxy exists (INTEGRATION.md §4)."""
    from app.config import AUDIENCE_QAGENT

    make_user("meta-agent@emesoft.net", PASSWORD)
    token = login("meta-agent@emesoft.net", PASSWORD)["tokens"][AUDIENCE_QAGENT]
    headers = {"Authorization": f"Bearer {token}"}

    assert client.get("/connections/1/work-item-metadata", headers=headers).status_code == 401
    assert client.delete("/connections/1/metadata/cache", headers=headers).status_code == 401
