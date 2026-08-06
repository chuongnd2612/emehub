"""Cached provider metadata — the query builder's pickers.

Reading a project's work-item types, states, area and iteration trees, members and
tags is four or five round trips to Azure DevOps, each spending the connection's
PAT. Doing that every time a filter panel opens is slow and rude to the provider,
so the payload is cached per connection with a TTL.

## Why a table and not a dict

An in-process cache diverges across uvicorn workers: two requests hit two workers
and see two different "fields read 4 minutes ago" answers, and a refresh warms only
the worker that served it. A row is shared, survives a restart, and makes the
staleness honest.

## Why the payload is opaque JSON

The shape belongs to the adapter, and it differs per provider. Modelling columns
here would mean a migration every time a picker gains a field, and this table is a
cache — nothing reads it except the code that wrote it, and a payload it cannot
parse is simply a miss.

No secrets are stored: the payload is names, paths and display names, the same
things the metadata endpoint already returns to the browser. The PAT is never part
of it.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, ForeignKey, Integer
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base, timestamp_column


class ProviderMetadataCache(Base):
    __tablename__ = "provider_metadata_cache"

    #: One row per connection — the cache key is the connection, because the
    #: payload is scoped to its organisation, project and credential.
    connection_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("provider_connections.id", ondelete="CASCADE"),
        primary_key=True,
    )
    #: The adapter's own metadata dict, verbatim.
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    #: When the payload was really read from the provider — what "read 4 minutes
    #: ago" is computed from. Not the row's update time: a failed refresh leaves
    #: this untouched, so the age keeps telling the truth.
    fetched_at: Mapped[datetime] = timestamp_column()
