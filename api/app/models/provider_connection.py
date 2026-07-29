"""Provider connection — a named account at Azure DevOps, GitHub or Jira.

Ported from QAgent's ``models/provider_connection.py`` (Phase 3 —
[ROADMAP](../../../docs/ROADMAP.md#phase-3--credentials)), with three
deliberate changes:

1. **Kinds are spelled out.** QAgent's ``ado`` becomes ``azure_devops``. The hub
   is the suite's public contract; a two-letter abbreviation in a wire enum is a
   thing every consumer has to learn.
2. **The PAT is its own column, not a bag.** QAgent keeps a ``secrets`` JSON
   dict of encrypted values. One nullable ``pat_encrypted`` column makes "the
   PAT never leaves the hub" (CLAUDE.md › Security rules) something you can
   verify by reading the schema: there is exactly one place a secret can live,
   and no serializer anywhere reads it. Jira's account *email* is not a secret
   and moves into ``config``; its API token is the ``pat``.
3. **Capabilities are stored, not derived.** QAgent derives them from the kind,
   so every GitHub connection is identical. Here the row carries its own list,
   defaulted from the kind's capabilities and constrained to what the kind's
   adapter actually implements — an operator can narrow a connection ("this
   GitHub account is for repositories only") without a second provider kind.

A connection advertises one or both capabilities:

* **work_item** — it supplies tickets / work items.
* **repository** — it supplies git repositories.

A kind can hold both. Azure DevOps serves work items *and* Git repos; so does
GitHub (issues and repositories). That is the whole point of the capability
model: a project binds a *different* connection per job if it wants to, rather
than one provider owning everything.

``owner_id`` is the hub's workspace scoping column (``app.services.ownership``):
a user id for a private connection, ``NULL`` for the workspace-wide shared
namespace.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, Boolean, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base, UTCDateTime, timestamp_column, utcnow

# ---------------------------------------------------------------- kinds
AZURE_DEVOPS = "azure_devops"
GITHUB = "github"
JIRA = "jira"

#: Fixed display order for the grouped catalog.
PROVIDER_KINDS: tuple[str, ...] = (AZURE_DEVOPS, GITHUB, JIRA)

PROVIDER_DISPLAY_NAMES: dict[str, str] = {
    AZURE_DEVOPS: "Azure DevOps",
    GITHUB: "GitHub",
    JIRA: "Jira",
}

# ---------------------------------------------------------- capabilities
WORK_ITEM = "work_item"
REPOSITORY = "repository"

CAPABILITIES: tuple[str, ...] = (WORK_ITEM, REPOSITORY)

#: What each kind's adapter can actually do. A connection may advertise a
#: *subset* of these; it may never advertise something outside them, because
#: the adapter has no code path for it.
SUPPORTED_CAPABILITIES: dict[str, tuple[str, ...]] = {
    # WIQL work items *and* Git repositories.
    AZURE_DEVOPS: (WORK_ITEM, REPOSITORY),
    # Issues are work items; repositories are repositories.
    GITHUB: (WORK_ITEM, REPOSITORY),
    # Issues only — Jira has no git hosting.
    JIRA: (WORK_ITEM,),
}


def supported_capabilities(kind: str) -> tuple[str, ...]:
    """Everything ``kind``'s adapter implements. Empty for an unknown kind."""
    return SUPPORTED_CAPABILITIES.get(kind, ())


def default_capabilities(kind: str) -> list[str]:
    """What a new connection of ``kind`` advertises unless told otherwise."""
    return list(supported_capabilities(kind))


class ProviderConnection(Base):
    """A named connection to an external provider account."""

    __tablename__ = "provider_connections"

    id: Mapped[int] = mapped_column(primary_key=True)
    #: azure_devops | github | jira. Not unique — a kind holds many accounts.
    kind: Mapped[str] = mapped_column(String(32), index=True)
    #: Human label, e.g. "EMESOFT — Surveyor".
    label: Mapped[str] = mapped_column(String(160), default="")
    #: Organisation / site URL: the ADO org URL, the Jira site, or a GitHub
    #: Enterprise API base. Empty for github.com.
    base_url: Mapped[str] = mapped_column(String(500), default="")
    #: Non-secret adapter fields (project, org, repo, email). Never a secret —
    #: ``connection_service.reject_secret_like_config`` enforces that on write.
    config: Mapped[dict] = mapped_column(JSON, default=dict)
    #: The **only** secret this table holds, always an ``enc::v1:`` envelope
    #: from :mod:`app.crypto`. Never serialized; see ``routers/connections.py``.
    pat_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    #: Subset of ``SUPPORTED_CAPABILITIES[kind]`` this connection advertises.
    capabilities: Mapped[list] = mapped_column(JSON, default=list)
    #: Last ``POST /connections/{id}/test`` verdict.
    connected: Mapped[bool] = mapped_column(Boolean, default=False)
    last_sync: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    last_tested_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    created_at: Mapped[datetime] = timestamp_column()
    updated_at: Mapped[datetime] = timestamp_column(onupdate=utcnow)
    #: Workspace scoping: NULL == the shared namespace (services/ownership.py).
    owner_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True
    )

    # ------------------------------------------------------------ derived
    @property
    def has_pat(self) -> bool:
        """Whether a PAT is stored. This is the *only* thing an API response is
        ever allowed to say about it (CLAUDE.md › "Endpoints return
        ``hasPat: true``, never the PAT")."""
        return bool(self.pat_encrypted)

    @property
    def shared(self) -> bool:
        return self.owner_id is None

    @property
    def display_name(self) -> str:
        return self.label or PROVIDER_DISPLAY_NAMES.get(self.kind, self.kind)

    def advertises(self, capability: str) -> bool:
        return capability in (self.capabilities or [])

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        # Deliberately excludes config and pat_encrypted: a repr ends up in
        # tracebacks and log lines, and neither may ever carry a secret.
        return f"<ProviderConnection id={self.id} kind={self.kind!r} label={self.label!r}>"
