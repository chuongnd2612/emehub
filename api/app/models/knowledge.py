"""Project Knowledge Base — the *metadata* record, ported from QAgent.

QAgent's knowledge lives in two places: a Postgres row and a pair of artifacts
(``knowledge.md`` + ``knowledge.json``) under a per-user workspace directory,
built by the ``project-bootstrap`` skill running the Claude CLI inside a repo
clone on the QAgent host.

**The hub owns both, now** ([ADR 0007](../../../docs/adr/0007-knowledge-builds-run-on-the-hub.md)).
It clones the repository, runs ``project-bootstrap`` and writes the artefact pair
into an owner-scoped workspace directory. It is not the *only* builder: QAgent
still builds its own and reports the result through
``PUT /projects/{key}/repos/{repo}/knowledge``.

``doc_path`` therefore means one of two things depending on who built the row,
and nothing in the schema distinguishes them because nothing needs to: a hub
build writes a path under ``EMEHUB_WORKSPACE_DIR``, an agent's report carries an
opaque agent-host path the hub stores and never resolves. Either way the hub
only ever *reads back* a path it wrote itself.

Rows are keyed by :func:`compose_key`, and uniqueness is scoped to
``(key, owner_id)`` so the same repo's knowledge can exist once per member and
once in the shared namespace.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, Boolean, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base, UTCDateTime, timestamp_column, utcnow

#: Lifecycle of a knowledge base. ``indexing`` is owned by whoever is building —
#: the hub itself for a ``POST …/knowledge/build`` (where it is also the
#: in-flight guard), or an agent that sets it through ``PUT …/knowledge``.
KNOWLEDGE_STATUSES = ("not_indexed", "indexing", "indexed", "stale", "error")

STATUS_NOT_INDEXED = "not_indexed"
STATUS_INDEXING = "indexing"
STATUS_INDEXED = "indexed"
STATUS_STALE = "stale"
STATUS_ERROR = "error"


#: The stages a hub-side build actually passes through, in order (issue #68).
#:
#: Every entry maps 1:1 onto work that really happens in
#: ``knowledge_service._build`` — there is no cosmetic step, and no stage is
#: entered before the work behind it starts. ``queued`` is a real state, not a
#: courtesy: over ``EMEHUB_KNOWLEDGE_BUILD_CONCURRENCY`` a worker blocks on the
#: semaphore with its row already ``indexing``, which from the outside is
#: indistinguishable from a build that is running unless it is recorded.
#:
#: ``build_step`` is the **1-based** ordinal of the stage, so ``0`` is
#: unambiguously "no build has ever recorded progress on this row".
BUILD_STAGES: tuple[str, ...] = (
    "queued",
    "resolving",
    "cloning",
    "analyzing",
    "writing",
)

BUILD_STAGE_QUEUED = "queued"
BUILD_STAGE_RESOLVING = "resolving"
BUILD_STAGE_CLONING = "cloning"
BUILD_STAGE_ANALYZING = "analyzing"
BUILD_STAGE_WRITING = "writing"

#: Total number of stages, so a client can render "step 3 of 5" without
#: hard-coding a number that would silently drift if a stage were added.
BUILD_TOTAL_STEPS = len(BUILD_STAGES)

#: The default human-readable line for each stage. A stage may replace it with
#: something more specific — the Claude stage does, continuously, from the CLI's
#: own event stream.
BUILD_STAGE_LABELS: dict[str, str] = {
    BUILD_STAGE_QUEUED: "Waiting for a build slot",
    BUILD_STAGE_RESOLVING: "Resolving the project configuration",
    BUILD_STAGE_CLONING: "Cloning the repository",
    BUILD_STAGE_ANALYZING: "Reading the repository with Claude",
    BUILD_STAGE_WRITING: "Writing the knowledge base",
}

#: How long a message may be once it reaches the column. The live message is
#: derived from Claude's stream, so it is bounded here as well as scrubbed.
BUILD_MESSAGE_LIMIT = 400


def build_step(stage: str) -> int:
    """1-based ordinal of ``stage``; ``0`` for anything unrecognised or blank."""
    try:
        return BUILD_STAGES.index(stage) + 1
    except ValueError:
        return 0


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
    #: Directory holding the emitted knowledge.md/.json — under the hub's
    #: workspace when the hub built it, opaque and agent-host when reported.
    doc_path: Mapped[str] = mapped_column(String(600), default="")
    #: Last build error (when status == "error"); cleared on success.
    last_error: Mapped[str] = mapped_column(String(1000), default="")

    # ── Build progress (issue #68) ─────────────────────────────────────────
    # DB-backed rather than in-memory on purpose: progress has to survive a
    # page reload, and it has to be readable by whichever worker answers the
    # poll, not only the one running the build.
    #: One of :data:`BUILD_STAGES`; "" when no build has recorded progress.
    build_stage: Mapped[str] = mapped_column(String(32), default="")
    #: 1-based ordinal of ``build_stage`` (0 = none), denormalised so a client
    #: renders "3 of 5" without knowing the stage vocabulary.
    build_step: Mapped[int] = mapped_column(Integer, default=0)
    #: The live human-readable line. During ``analyzing`` this is derived from
    #: the Claude CLI's event stream, so it is scrubbed and truncated before it
    #: ever gets here.
    build_message: Mapped[str] = mapped_column(String(BUILD_MESSAGE_LIMIT), default="")
    #: When the current (or last) build started. The UI's elapsed clock, and
    #: half of the orphan test.
    build_started_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    #: Last time a live worker touched this row. The other half of the orphan
    #: test: a row left ``indexing`` by a container that died stops being
    #: refreshed, and after ``EMEHUB_KNOWLEDGE_BUILD_STALE_S`` it is provably
    #: abandoned rather than merely slow.
    build_heartbeat_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)

    created_at: Mapped[datetime] = timestamp_column()
    updated_at: Mapped[datetime] = timestamp_column(onupdate=utcnow)
    # Workspace scoping: NULL == shared. See app.services.ownership.
    owner_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True
    )
