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

from typing import TypeVar

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.project import Project
from app.models.user import User
from app.services.ownership import can_write_shared, stamp_owner

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


def get_project(db: Session, key: str, user: User | None) -> Project | None:
    """Resolve one project by key with own → shared precedence."""
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
