"""Read provider metadata, cached, with an honest staleness answer.

The query builder's pickers are only as good as this: work-item types with their
own states, the area and iteration trees, members and tags. Reading them is several
provider round trips spending the connection's PAT, so the payload is cached per
connection.

## The three answers, and why they are three

* **fresh** — inside the TTL, served from the row, provider untouched.
* **refreshed** — TTL passed (or the caller asked), read again, row updated.
* **stale** — TTL passed, the refresh *failed*, and the cached payload is served
  anyway with ``stale=True`` and the reason.

That third one is the point. A filter panel whose metadata read failed must stay
**usable** — the values from an hour ago are almost certainly still right, and
offering them beats an empty picker that silently builds a query matching nothing.
It says so rather than pretending, which is the same rule the rest of the hub
follows: a failed load is never rendered as "no data".

A first read that fails has nothing to fall back on, so it raises.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from sqlalchemy.orm import Session

from app.config import settings
from app.db import utcnow
from app.logging import logger
from app.models.metadata_cache import ProviderMetadataCache
from app.models.provider_connection import ProviderConnection


class MetadataResult:
    """A metadata payload plus how much to trust its age."""

    def __init__(
        self,
        payload: dict[str, Any],
        fetched_at: Any,
        *,
        stale: bool = False,
        message: str = "",
    ) -> None:
        self.payload = payload
        self.fetched_at = fetched_at
        #: The TTL passed and the refresh we tried failed. The payload is the last
        #: good one, not an empty shell.
        self.stale = stale
        #: Plain-language cause of that failed refresh, for the UI to print.
        self.message = message


def ttl() -> timedelta:
    return timedelta(minutes=settings.metadata_ttl_minutes)


def _entry(db: Session, connection_id: int) -> ProviderMetadataCache | None:
    return db.get(ProviderMetadataCache, connection_id)


def _store(db: Session, connection_id: int, payload: dict[str, Any]) -> ProviderMetadataCache:
    row = _entry(db, connection_id)
    now = utcnow()
    if row is None:
        row = ProviderMetadataCache(connection_id=connection_id, payload=payload, fetched_at=now)
        db.add(row)
    else:
        row.payload = payload
        row.fetched_at = now
        db.add(row)
    db.commit()
    db.refresh(row)
    return row


def clear(db: Session, connection_id: int) -> bool:
    """Drop the cached payload. True when there was one."""
    row = _entry(db, connection_id)
    if row is None:
        return False
    db.delete(row)
    db.commit()
    return True


def read(
    db: Session,
    connection: ProviderConnection,
    load: Any,
    *,
    refresh: bool = False,
) -> MetadataResult:
    """Metadata for ``connection``, from cache or the provider.

    ``load`` is a zero-argument callable that performs the real read — injected so
    this module never builds an adapter, and so tests can drive every branch
    without HTTP.
    """
    row = _entry(db, connection.id)
    expired = row is None or (utcnow() - row.fetched_at) >= ttl()

    if row is not None and not expired and not refresh:
        return MetadataResult(dict(row.payload or {}), row.fetched_at)

    try:
        payload = load()
    except Exception as exc:  # noqa: BLE001 — any provider failure, deliberately
        if row is None:
            # Nothing cached to fall back on: a first read that fails is a
            # failure, not an empty picker.
            raise
        logger.warning(
            "Metadata refresh failed for connection %s; serving the cached payload: %s",
            connection.id,
            exc,
        )
        return MetadataResult(
            dict(row.payload or {}),
            row.fetched_at,
            stale=True,
            message=str(exc) or "The provider did not answer.",
        )

    stored = _store(db, connection.id, payload or {})
    return MetadataResult(dict(stored.payload or {}), stored.fetched_at)
