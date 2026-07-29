"""Project knowledge — metadata persistence and the discovery merge.

Ported from QAgent's ``services/knowledge_service.py``, **metadata parts only**.

## What is NOT here, and why

QAgent's module is mostly a *builder*: it renders a prompt, runs the Claude CLI
inside a repo clone (``run_json(..., cwd=repo_path)``), spawns a background
thread per build, and writes ``knowledge.md`` + ``knowledge.json`` into a
per-user workspace directory. Every one of those needs a filesystem, a clone and
a Claude credential on disk, and the hub has none of the three
(ROADMAP.md Phase 4; CLAUDE.md — the hub does no domain work). So:

* ``build_knowledge_payload`` / ``_build_prompt`` / ``start_build`` — not ported.
  Building stays on the agent host.
* ``write_knowledge_files`` — not ported. See the *filesystem seams* note at the
  bottom for exactly what the agent still owns.
* ``apply_build`` — ported as :func:`apply_build_result`, minus the file write:
  the agent builds and then *reports* the result through
  ``PUT /projects/{key}/repos/{repo}/knowledge``.

## What IS here

The row lifecycle (:data:`app.models.knowledge.KNOWLEDGE_STATUSES`) and the
write path in INTEGRATION.md §3 — :func:`merge_discovery`, the port of QAgent's
``merge_verified_discovery`` / ``merge_discovered_dom``.

### The merge rule

An agent that drives the live application observes routes and selectors that
are, by definition, runtime facts. Merging them must never *lose* a fact:

* **dedup** by ``path`` (routes) and by ``selector`` value (selectors);
* **no-clobber** — an existing entry already carrying a truthy
  ``verified_at_runtime`` is left exactly as it is and the colliding incoming
  entry is dropped. Runtime-verified beats source-inferred, and it also beats a
  *later* runtime observation, because the first verification is the one a
  human may have since acted on;
* an incoming entry colliding with an **unverified** (source-inferred) entry
  **upgrades it in place**, preserving the existing entry's other keys;
* anything that collides with nothing is appended.

Every merged or upgraded entry is stamped ``verified_at_runtime`` (ISO-8601 UTC)
and ``source``; selectors additionally carry the ``strategy`` that worked.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.db import utcnow
from app.models.knowledge import (
    KNOWLEDGE_STATUSES,
    STATUS_INDEXED,
    STATUS_NOT_INDEXED,
    ProjectKnowledge,
    compose_key,
)
from app.models.user import User
from app.services import project_service
from app.services.ownership import stamp_owner


# ------------------------------------------------------------------- reads
def get_knowledge(
    db: Session, project_key: str, repo: str, user: User | None
) -> ProjectKnowledge | None:
    """The knowledge row visible to ``user`` — own → shared → ``None``.

    A per-repo read falls back to the project-level row (``repo=""``) when the
    repo has no row of its own, mirroring QAgent's resolution so an agent asking
    for ``repos/web/knowledge`` on a project that only ever built project-level
    knowledge still gets grounding instead of a 404.
    """
    row = project_service.own_then_shared(
        db,
        ProjectKnowledge,
        user,
        ProjectKnowledge.key == compose_key(project_key, repo),
    )
    if row is None and repo:
        row = project_service.own_then_shared(
            db, ProjectKnowledge, user, ProjectKnowledge.key == project_key
        )
    return row


def list_knowledge(db: Session, project_key: str, user: User | None) -> list[ProjectKnowledge]:
    """Every knowledge row for a project that ``user`` may see (own + shared),
    the owned row winning where both namespaces hold the same key."""
    from app.services.ownership import owned

    rows = owned(db.query(ProjectKnowledge), ProjectKnowledge, user).filter(
        ProjectKnowledge.project_key == project_key
    ).all()
    by_key: dict[str, ProjectKnowledge] = {}
    for row in rows:
        current = by_key.get(row.key)
        if current is None or (current.owner_id is None and row.owner_id is not None):
            by_key[row.key] = row
    return [by_key[key] for key in sorted(by_key)]


# ------------------------------------------------------------------- writes
def write_target(
    db: Session, project_key: str, repo: str, user: User | None, *, create: bool = True
) -> ProjectKnowledge | None:
    """Resolve the row a write lands on, creating it when asked.

    Precedence, and the reason for each step:

    1. the caller's **own** row — always the first choice;
    2. the **shared** row, but only when the caller may write the shared
       namespace (``ownership.can_write_shared`` → admins). A member must not be
       able to edit knowledge everyone reads;
    3. otherwise a **new row owned by the caller**. A member's contribution is
       kept, in their own namespace, instead of being dropped or leaking into
       everyone's.

    Returns ``None`` only when ``create`` is False and nothing writable exists.
    """
    from app.services.ownership import can_write_shared

    key = compose_key(project_key, repo)
    if user is not None:
        own = (
            db.query(ProjectKnowledge)
            .filter(ProjectKnowledge.key == key, ProjectKnowledge.owner_id == user.id)
            .first()
        )
        if own is not None:
            return own
    if can_write_shared(user):
        shared = (
            db.query(ProjectKnowledge)
            .filter(ProjectKnowledge.key == key, ProjectKnowledge.owner_id.is_(None))
            .first()
        )
        if shared is not None:
            return shared
    if not create:
        return None
    row = ProjectKnowledge(
        key=key,
        project_key=project_key,
        repo=repo,
        name=project_key,
        status=STATUS_NOT_INDEXED,
    )
    stamp_owner(row, user)
    db.add(row)
    return row


def apply_metadata(row: ProjectKnowledge, patch: dict[str, Any]) -> None:
    """Apply the descriptive (non-lifecycle) fields of a patch, in place."""
    for field in ("name", "provider", "framework", "doc_path"):
        if patch.get(field) is not None:
            setattr(row, field, patch[field])


def apply_build_result(
    row: ProjectKnowledge,
    *,
    knowledge: dict[str, Any] | None = None,
    confidence: int | None = None,
    status: str | None = None,
    doc_path: str | None = None,
    last_error: str | None = None,
    needs_refresh: bool | None = None,
) -> None:
    """Record a build outcome reported by the agent. Caller commits.

    Ported from QAgent's ``apply_build`` **without the file write** — the agent
    already wrote its own artifacts and tells us where (``doc_path``).

    Version semantics are QAgent's: the first successful index stays ``v1``,
    every subsequent one increments. A transition to ``indexed`` also stamps
    ``last_indexed``, clears ``needs_refresh`` and clears ``last_error`` —
    a stale error message on a healthy row reads as an outage that isn't
    happening.
    """
    if status is not None:
        if status not in KNOWLEDGE_STATUSES:
            raise ValueError(f"Unknown knowledge status '{status}'")
        becoming_indexed = status == STATUS_INDEXED
        if becoming_indexed:
            row.version = _next_version(row)
            row.last_indexed = utcnow()
            row.needs_refresh = False
            row.last_error = ""
        row.status = status
    if knowledge is not None:
        row.knowledge = knowledge
    if confidence is not None:
        row.confidence = max(0, min(100, int(confidence)))
    if doc_path is not None:
        row.doc_path = doc_path
    if last_error is not None:
        row.last_error = last_error[:1000]
    if needs_refresh is not None:
        row.needs_refresh = bool(needs_refresh)


def _next_version(row: ProjectKnowledge) -> str:
    """``v1`` for a first index, ``v(n+1)`` for a rebuild."""
    if row.last_indexed is None:
        return "v1"
    try:
        n = int((row.version or "v1").lstrip("v") or "1")
    except ValueError:
        n = 1
    return f"v{n + 1}"


# ------------------------------------------------------------------- merge
def merge_discovery(
    row: ProjectKnowledge, discovered: dict[str, Any], *, source: str = "exploration"
) -> int:
    """Merge runtime-discovered routes/selectors into ``row``. Caller commits.

    See the module docstring for the rule. Returns the number of entries
    appended or upgraded; ``0`` means nothing changed, including the case where
    every incoming entry collided with an already-verified one.

    Unlike QAgent's version this takes the row rather than looking it up, opens
    no session of its own and writes no files — the caller (the PATCH endpoint)
    already resolved and authorised the row inside its own transaction.
    """
    now = datetime.now(timezone.utc).isoformat()
    routes_in = [
        r
        for r in (discovered.get("routes") or [])
        if isinstance(r, dict) and (r.get("path") or "").strip()
    ]
    selectors_in = [
        s
        for s in (discovered.get("selectors") or [])
        if isinstance(s, dict) and (s.get("selector") or "").strip()
    ]
    if not routes_in and not selectors_in:
        return 0

    knowledge = dict(row.knowledge or {})
    merged = 0

    if routes_in:
        routes = list(knowledge.get("routes") or [])
        merged += _merge_entries(
            routes,
            routes_in,
            field="path",
            stamp=lambda entry: {**entry, "verified_at_runtime": now, "source": source},
        )
        knowledge["routes"] = routes

    if selectors_in:
        selectors = list(knowledge.get("selectors") or [])
        merged += _merge_entries(
            selectors,
            selectors_in,
            field="selector",
            stamp=lambda entry: {
                **entry,
                "strategy": entry.get("strategy") or "css",
                "verified_at_runtime": now,
                "source": source,
            },
        )
        knowledge["selectors"] = selectors

    if not merged:
        return 0
    # Reassign so SQLAlchemy tracks the JSON mutation.
    row.knowledge = knowledge
    return merged


def _merge_entries(existing: list, incoming: list[dict], *, field: str, stamp) -> int:
    """Dedup-by-``field`` merge with the no-clobber rule. Mutates ``existing``."""
    index: dict[str, int] = {}
    for i, entry in enumerate(existing):
        if isinstance(entry, dict) and entry.get(field):
            index.setdefault(entry[field], i)

    merged = 0
    for raw in incoming:
        value = raw[field].strip()
        entry = stamp({**raw, field: value})
        i = index.get(value)
        if i is None:
            existing.append(entry)
            index[value] = len(existing) - 1
            merged += 1
        elif existing[i].get("verified_at_runtime"):
            # No-clobber: a runtime-verified entry is never overwritten.
            continue
        else:
            # Upgrade a source-inferred entry in place, keeping its other keys.
            existing[i] = {**existing[i], **entry}
            merged += 1
    return merged


# ----------------------------------------------------------- filesystem seams
#
# Three things QAgent's knowledge_service does that the hub deliberately does
# NOT, and which the agent must therefore keep doing:
#
# 1. **Clone / pull the repository.** QAgent's ``_resolve_path_for_row`` resolves
#    a checkout (using the row owner's own repository-connection PAT) before a
#    build. The hub never clones: it holds no clone, and handing out the PAT to
#    make one possible is exactly what CLAUDE.md forbids.
#
# 2. **Run ``project-bootstrap`` through the Claude CLI.** The build reads real
#    source with the CLI's file tools, in the clone, with a credential on disk.
#    The hub does no Claude invocation for end-user tasks (CLAUDE.md).
#
# 3. **Write ``knowledge.md`` + ``knowledge.json``.** These are the skill's
#    artifacts, consumed by downstream skills running on the same host. The hub
#    stores only ``doc_path``, an opaque agent-host string.
#
# The seam is the HTTP write path: the agent builds, writes its own artifacts,
# then reports the outcome with
# ``PUT  /projects/{key}/repos/{repo}/knowledge``   (status/knowledge/confidence/doc_path)
# and contributes runtime discoveries with
# ``PATCH /projects/{key}/repos/{repo}/knowledge``  (:func:`merge_discovery`).
# A row moving to ``indexing`` and never coming back means the agent died
# mid-build; the hub does not time it out, because only the agent knows.
