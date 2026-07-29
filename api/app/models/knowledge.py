"""Project Knowledge Base — the *metadata* record, ported from QAgent.

QAgent's knowledge lives in two places: a Postgres row and a pair of artifacts
(``knowledge.md`` + ``knowledge.json``) under a per-user workspace directory,
built by the ``project-bootstrap`` skill running the Claude CLI inside a repo
clone on the QAgent host.

**The hub owns the row, not the filesystem** (ROADMAP.md Phase 4 — "the hard
part is not the data, it is the filesystem"). The hub never clones a repository,
never runs ``project-bootstrap`` and owns no workspace directory. ``doc_path``
is therefore an opaque *agent-host* path the agent reports and the hub stores so
the agent can find its own artifacts again — the hub never resolves or reads it.

Rows are keyed by :func:`compose_key`, and uniqueness is scoped to
``(key, owner_id)`` so the same repo's knowledge can exist once per member and
once in the shared namespace.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, Boolean, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base, UTCDateTime, timestamp_column, utcnow

#: Lifecycle of a knowledge base. ``indexing`` is owned by whoever is building
#: (the agent); the hub only records the transition it is told about.
KNOWLEDGE_STATUSES = ("not_indexed", "indexing", "indexed", "stale", "error")

STATUS_NOT_INDEXED = "not_indexed"
STATUS_INDEXING = "indexing"
STATUS_INDEXED = "indexed"
STATUS_STALE = "stale"
STATUS_ERROR = "error"


def compose_key(project_key: str, repo: str = "") -> str:
    """Row key for a project's (optionally repo-scoped) knowledge base.

    Per-repo rows use ``"<project>::<repo>"``; a blank repo yields the bare
    project key (project-level knowledge). Kept byte-identical to QAgent's
    function so a row exported from one side is addressable on the other.
    """
    return f"{project_key}::{repo}" if repo else project_key


def split_key(key: str) -> tuple[str, str]:
    """Inverse of :func:`compose_key` — ``("<project>", "<repo>")``.

    A key without the separator is project-level, so the repo is ``""``.
    """
    project, sep, repo = key.partition("::")
    return (project, repo) if sep else (key, "")


class ProjectKnowledge(Base):
    __tablename__ = "project_knowledge"
    __table_args__ = (
        UniqueConstraint("key", "owner_id", name="uq_project_knowledge_key_owner"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    #: ``compose_key(project_key, repo)``.
    key: Mapped[str] = mapped_column(String(320), index=True)
    #: The owning project. Many repos → many rows sharing one ``project_key``.
    project_key: Mapped[str] = mapped_column(String(200), default="", index=True)
    name: Mapped[str] = mapped_column(String(200), default="")
    provider: Mapped[str] = mapped_column(String(64), default="")
    #: The repository this knowledge base describes ("" = project-level).
    repo: Mapped[str] = mapped_column(String(300), default="")
    framework: Mapped[str] = mapped_column(String(64), default="Playwright")

    status: Mapped[str] = mapped_column(String(16), default=STATUS_NOT_INDEXED, index=True)
    confidence: Mapped[int] = mapped_column(Integer, default=0)
    version: Mapped[str] = mapped_column(String(16), default="v1")
    needs_refresh: Mapped[bool] = mapped_column(Boolean, default=False)
    last_indexed: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)

    #: {branch, stack[], architecture, domain, locator, base_url, routes[],
    #:  selectors[], auth{}, environments[], business_entities[], …}
    knowledge: Mapped[dict] = mapped_column(JSON, default=dict)
    #: Agent-host directory holding the emitted knowledge.md/.json. Opaque here.
    doc_path: Mapped[str] = mapped_column(String(600), default="")
    #: Last build error (when status == "error"); cleared on success.
    last_error: Mapped[str] = mapped_column(String(1000), default="")

    created_at: Mapped[datetime] = timestamp_column()
    updated_at: Mapped[datetime] = timestamp_column(onupdate=utcnow)
    # Workspace scoping: NULL == shared. See app.services.ownership.
    owner_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True
    )
