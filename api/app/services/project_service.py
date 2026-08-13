"""Project registry — list, resolve and upsert :class:`app.models.project.Project`.

Also home to :func:`own_then_shared`, the resolution rule the whole slice uses.

## own → shared → none

Every project-scoped table is keyed by a *name*, not a surrogate id, and the
same name may exist twice: once owned by the caller and once in the shared
namespace (``owner_id IS NULL``). Which one a read returns is therefore a
decision, not an accident, and it is made in exactly one place here so the
project, its config and its knowledge never disagree about which row they mean.

The order mirrors the credential precedence in INTEGRATION.md §3 — **own wins,
shared is the fallback, nothing else is ever visible**. Another member's
same-keyed row is invisible: it is not returned, and its absence is reported as
a 404, never a 403 (a 403 would confirm it exists).
"""

from __future__ import annotations

import shutil
import uuid
from pathlib import Path
from typing import TypeVar

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.project import Project
from app.models.user import User
from app.services.ownership import can_write_shared, stamp_owner
from app.services.workspace_scope import slug

ModelT = TypeVar("ModelT")


def own_then_shared(
    db: Session, model: type[ModelT], user: User | None, *filters
) -> ModelT | None:
    """The caller's own row matching ``filters``, else the shared one, else ``None``.

    Never returns another member's row — the two queries pin ``owner_id`` to
    either the caller or ``NULL``, so there is no filter to get wrong.
    """
    if user is None:
        return None
    own = db.query(model).filter(*filters, model.owner_id == user.id).first()
    if own is not None:
        return own
    return db.query(model).filter(*filters, model.owner_id.is_(None)).first()


def for_owner(db: Session, model: type[ModelT], owner_id: int | None, *filters) -> ModelT | None:
    """The row for one *specific* namespace — the caller's, or shared when
    ``owner_id`` is ``None``. Used by writes, which must never fall back."""
    scope = model.owner_id.is_(None) if owner_id is None else model.owner_id == owner_id
    return db.query(model).filter(*filters, scope).first()


# ------------------------------------------------------------------ projects
def list_projects(db: Session, user: User | None) -> list[Project]:
    """Projects visible to ``user``: their own, plus the shared namespace.

    A key present in both namespaces is collapsed to the owned row — the same
    own → shared precedence a single-key read applies, so the list and the
    detail endpoint never show a different project for one key.
    """
    from app.services.ownership import owned

    rows = owned(db.query(Project), Project, user).order_by(Project.key).all()
    by_key: dict[str, Project] = {}
    for row in rows:
        current = by_key.get(row.key)
        if current is None or (current.owner_id is None and row.owner_id is not None):
            by_key[row.key] = row
    return [by_key[key] for key in sorted(by_key)]


def looks_like_guid(value: str) -> bool:
    """Is this the GUID form? Shape only — it says nothing about existence."""
    try:
        # `UUID()` accepts several spellings (braced, `urn:`, undashed). Comparing
        # the canonical round-trip against the input keeps this to the one form we
        # issue, so a near-miss is treated as a key rather than as a malformed id.
        return str(uuid.UUID(value)) == value.lower()
    except (ValueError, AttributeError, TypeError):
        return False


def get_project(db: Session, key: str, user: User | None) -> Project | None:
    """Resolve one project by **GUID or key**, with own → shared precedence.

    A GUID is matched as a GUID and nothing else (#150). The tempting alternative
    — try it as a key first and fall back to the GUID — would let a project whose
    key happened to be spelled like a UUID shadow the project that GUID belongs
    to, and only for whoever owned the impostor. Identity that depends on lookup
    order is not identity.

    GUIDs are globally unique, so the own → shared precedence is moot on that
    branch: there is at most one row, and the usual scoping still decides whether
    this caller may see it.
    """
    if looks_like_guid(key):
        return own_then_shared(db, Project, user, Project.guid == key.lower())
    return own_then_shared(db, Project, user, Project.key == key)


def summaries_for(
    db: Session, rows: list[Project], user: User | None
) -> dict[str, dict]:
    """Per-project card figures for a whole list, in three queries total.

    The client used to assemble these itself, costing ``GET config`` +
    ``GET tickets?projectId=`` + one or two ``GET knowledge`` **per project** —
    3N+1 requests to draw one screen.

    Only non-secret scalars are returned. In particular **no test-account
    material, not even ``hasPassword``** — the list response deliberately
    carries none of it (see ``list_projects`` in the router), and that must
    stay true now that the payload is richer.
    """
    from app.models.knowledge import ProjectKnowledge
    from app.models.project_config import ProjectConfig
    from app.models.ticket import Ticket
    from app.services.ownership import owned

    if not rows:
        return {}

    keys = [r.key for r in rows]
    ids = [r.id for r in rows]

    # own → shared precedence, applied the same way `list_projects` does.
    def collapse(items, key_of):
        best: dict[str, object] = {}
        for item in items:
            k = key_of(item)
            current = best.get(k)
            if current is None or (
                getattr(current, "owner_id", None) is None
                and item.owner_id is not None
            ):
                best[k] = item
        return best

    configs = collapse(
        owned(db.query(ProjectConfig), ProjectConfig, user)
        .filter(ProjectConfig.key.in_(keys))
        .all(),
        lambda c: c.key,
    )
    knowledge = collapse(
        owned(db.query(ProjectKnowledge), ProjectKnowledge, user)
        .filter(ProjectKnowledge.project_key.in_(keys))
        .all(),
        lambda k: k.project_key,
    )

    counts: dict[int, int] = {}
    for project_id, total in (
        owned(db.query(Ticket.project_id, func.count(Ticket.id)), Ticket, user)
        .filter(Ticket.project_id.in_(ids))
        .group_by(Ticket.project_id)
        .all()
    ):
        counts[project_id] = total

    summaries: dict[str, dict] = {}
    for row in rows:
        config = configs.get(row.key)
        repos = list(getattr(config, "repos", None) or [])
        default_repo = next(
            (r for r in repos if isinstance(r, dict) and r.get("default")),
            repos[0] if repos and isinstance(repos[0], dict) else None,
        )
        know = knowledge.get(row.key)
        summaries[row.key] = {
            "repo": (default_repo or {}).get("name", "") or "",
            "repo_url": (default_repo or {}).get("repo_url", "") or "",
            "branch": (default_repo or {}).get("default_branch", "") or "",
            "repo_count": len(repos),
            "provider": getattr(know, "provider", "") or "",
            "knowledge_status": getattr(know, "status", "") or "not_indexed",
            "knowledge_confidence": getattr(know, "confidence", 0) or 0,
            "ticket_count": counts.get(row.id, 0),
        }
    return summaries


def write_target_owner(user: User | None, *, shared: bool) -> int | None:
    """Which namespace a write lands in.

    ``shared=True`` is admin-only (``ownership.can_write_shared``); anyone else
    asking for it writes their own row instead of silently editing everyone's.
    """
    if shared and can_write_shared(user):
        return None
    return user.id if user is not None else None


class ProjectHasTickets(Exception):
    """A delete was refused because work items still point at the project.

    Carries the count so the router can say how many without re-querying.
    """

    def __init__(self, count: int) -> None:
        self.count = count
        super().__init__(f"{count} ticket(s) still reference this project")


def _scoped_project_dir(base: Path, key: str) -> Path | None:
    """``base/slug(key)``, but only if it really is inside ``base``.

    ``slug`` already collapses ``/`` and ``..`` into ``-``, so this cannot
    currently fail — which is the point of checking it here rather than trusting
    that it stays true. The argument is a user-supplied project key and the
    consequence of being wrong is ``rmtree`` on a directory outside the scope,
    so the containment is asserted at the point of deletion, not inferred.
    """
    resolved_base = base.resolve()
    candidate = (base / slug(key)).resolve()
    if candidate == resolved_base or resolved_base not in candidate.parents:
        return None
    return candidate


def delete_project(db: Session, row: Project) -> dict[str, int]:
    """Delete ``row`` and everything the hub owns *about* it. Caller commits.

    Cascades, all pinned to the project's own namespace (``row.owner_id``) so
    deleting a private project can never touch the shared one of the same key,
    or another member's:

    * ``project_config`` — the connection bindings, base URL, environments and
      the encrypted test-account passwords;
    * ``project_knowledge`` — every row for the project, per-repo rows included
      (they are keyed by ``project_key``, not by the composed ``key``);
    * the workspace directories — the shallow clone under ``repos/`` and the
      built ``knowledge.md``/``knowledge.json`` under ``knowledge/``.

    **Tickets are not cascaded.** Raises :class:`ProjectHasTickets` instead when
    any still reference the row. A ticket is a mirror of a real work item in
    Azure DevOps or Jira, and it is the only hub-side record that a work item
    was ever synced; deleting a batch of them as a side effect of tidying up the
    registry destroys strictly more than the user asked to destroy, and it is
    not undoable from the hub (a re-sync needs the connection that was bound to
    the project being deleted). Detaching them is worse — ``project_id`` would
    dangle at a row that no longer exists, which is the orphaning this is meant
    to avoid. So the delete refuses, says how many are in the way, and
    ``DELETE /tickets/{external_id}`` is the deliberate second step.

    The directories go before the caller commits, so a failed commit leaves
    them removed while the rows survive. That is the harmless direction: both
    trees are derived artefacts the hub regenerates on the next build (the clone
    is shallow and re-cloned on demand), whereas deleting rows first and then
    failing would leave plaintext-adjacent clones behind with nothing pointing
    at them.

    Returns the counts that were removed, for the audit line.
    """
    from app.models.knowledge import ProjectKnowledge
    from app.models.project_config import ProjectConfig
    from app.models.ticket import Ticket
    from app.services.workspace_scope import scoped_knowledge_dir, scoped_repos_dir

    def _own_scope(model):
        """The project's own namespace — never a fallback to shared.

        ``owner_id == None`` renders as ``owner_id = NULL``, which is never
        true, so the shared namespace has to be matched with ``IS NULL``. Get
        this wrong on the ticket count and a shared project deletes silently
        with its work items still pointing at a row that is gone.
        """
        return (
            model.owner_id.is_(None)
            if row.owner_id is None
            else model.owner_id == row.owner_id
        )

    tickets = (
        db.query(Ticket)
        .filter(Ticket.project_id == row.id, _own_scope(Ticket))
        .count()
    )
    if tickets:
        raise ProjectHasTickets(tickets)

    configs = (
        db.query(ProjectConfig)
        .filter(ProjectConfig.key == row.key, _own_scope(ProjectConfig))
        .delete(synchronize_session=False)
    )
    knowledge = (
        db.query(ProjectKnowledge)
        .filter(
            ProjectKnowledge.project_key == row.key, _own_scope(ProjectKnowledge)
        )
        .delete(synchronize_session=False)
    )
    db.delete(row)

    for base in (scoped_repos_dir(row.owner_id), scoped_knowledge_dir(row.owner_id)):
        target = _scoped_project_dir(base, row.key)
        if target is not None and target.is_dir():
            shutil.rmtree(target, ignore_errors=True)

    return {"configs": configs, "knowledge": knowledge}


def upsert_project(
    db: Session, key: str, *, name: str | None, user: User | None, shared: bool = False
) -> Project:
    """Create or rename a project in the caller's (or the shared) namespace.

    Caller commits. Never touches another member's same-keyed row: the lookup is
    pinned to the resolved target namespace.
    """
    owner_id = write_target_owner(user, shared=shared)
    row = for_owner(db, Project, owner_id, Project.key == key)
    if row is None:
        row = Project(key=key, name=name or key)
        row.owner_id = owner_id
        if owner_id is not None:
            stamp_owner(row, user)
        db.add(row)
    elif name:
        row.name = name
    return row
