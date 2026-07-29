"""Project configuration — the user-authored runtime settings for a project.

Ported from QAgent's ``models/project_config.py``. Holds what a human configures
on the Project screen and what downstream automation needs in order to emit
runnable specs without placeholders: the application URL, the repositories,
per-environment URLs, and the test accounts.

**Test-account passwords are encrypted at rest** through :mod:`app.crypto`
(``enc::v1:`` envelope over ``EMEHUB_ENCRYPTION_KEY``) and are returned by the
API *only to the owning user* — INTEGRATION.md §3 says so explicitly. They are
never present in a list response and never logged.

## What is deliberately absent

QAgent's legacy single-repo fields (``local_repo_path`` / ``repo_url``) are not
ported: they were already superseded by ``repos`` there, and a hub-level "local
path" would be meaningless — **the hub owns no workspace filesystem** (see the
module docstring of :mod:`app.services.project_config_service`). A per-repo
``localRepoPath`` still travels inside a ``repos[]`` entry, but it is an
*agent-host* path the hub only stores and echoes back; the hub never resolves,
creates or reads it.

## The two connection columns

``work_item_connection_id`` / ``repository_connection_id`` bind a project to the
provider connections that serve its tickets and its code (QAgent ADR 0006). The
``provider_connections`` table is built by a parallel slice, so the columns are
declared here as plain nullable integers and the FK is *not* asserted at the
database level — see the migration for the full reasoning. Nothing in this
module imports the connections slice.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base, timestamp_column, utcnow


class ProjectConfig(Base):
    __tablename__ = "project_config"
    # The same project ``key`` can exist once per owner and once in the shared
    # namespace (``owner_id IS NULL``), so uniqueness is scoped to the pair.
    __table_args__ = (
        UniqueConstraint("key", "owner_id", name="uq_project_config_key_owner"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    # Matches Project.key and ProjectKnowledge.project_key.
    key: Mapped[str] = mapped_column(String(200), index=True)
    name: Mapped[str] = mapped_column(String(200), default="")

    # Per-project provider bindings. Plain integers on purpose: the referenced
    # table lands with the connections slice, and this slice must not depend on
    # its module or its migration ordering. Both nullable — an unbound project
    # degrades to whatever the agent resolves for itself.
    work_item_connection_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    repository_connection_id: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Primary application URL the generated automation targets.
    base_url: Mapped[str] = mapped_column(String(500), default="")
    # Repositories belonging to this project. Each entry:
    # {name, repo_url, default_branch, local_repo_path, default}. ``local_repo_path``
    # is an AGENT-HOST path — stored and echoed, never touched by the hub.
    repos: Mapped[list] = mapped_column(JSON, default=list)

    # [{ "name": str, "base_url": str, "notes": str }]
    environments: Mapped[list] = mapped_column(JSON, default=list)
    # [{ "role": str, "username": str, "password": <enc::v1:…>, "notes": str }]
    test_accounts: Mapped[list] = mapped_column(JSON, default=list)
    # Arbitrary project-specific values downstream generation may reference.
    extra: Mapped[dict] = mapped_column(JSON, default=dict)

    # When True, a run captures a real (headed) browser login before executing
    # specs and reuses the saved storageState. The capture itself happens on the
    # agent — the hub only records the intent.
    manual_auth: Mapped[bool] = mapped_column(default=False)

    created_at: Mapped[datetime] = timestamp_column()
    updated_at: Mapped[datetime] = timestamp_column(onupdate=utcnow)
    # Workspace scoping: NULL == shared. See app.services.ownership.
    owner_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True
    )
