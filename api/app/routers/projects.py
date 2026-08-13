"""Projects, project configuration and project knowledge.

Ported from QAgent's ``routers/projects.py``, minus everything that needs a
browser (``/auth/capture``, ``/explore``) — that stays on the agent host. What
remains is the registry, the configuration, the knowledge metadata, and — since
[ADR 0007](../../../docs/adr/0007-knowledge-builds-run-on-the-hub.md) — the
knowledge **build**.

## The build endpoint

``POST /{key}/repos/{repo}/knowledge/build`` is ``require_user``: hub audience
only. A build clones a repository, runs a Claude CLI process for minutes and
spends money, and none of those are things an agent's token should be able to
trigger on the hub's behalf. It returns ``202`` with the row already at
``indexing``; the UI polls ``GET …/knowledge`` for the outcome.

## Auth posture — CONTRACT, with hub-only writes

The router is registered ``CONTRACT`` in ``main.ROUTERS``: the blanket
dependency is ``require_principal``, so a token minted for **any registered
audience** is accepted. That is required — the four endpoints in the contract
(``GET /projects``, ``GET …/config``, ``GET …/knowledge``,
``PATCH …/knowledge``) are called by an agent with the token it holds
(``aud: "qagent"``), not with a hub token. An unregistered audience is still
refused, by both the blanket dependency and the guard middleware.

Managing the hub is a different matter, so the mutating endpoints that are *not*
in the contract (creating a project, saving a config) each declare
``Depends(require_user)`` on top, which pins them to ``aud: "emehub"``. An agent
token can read a project and contribute knowledge; it cannot create projects or
rewrite test accounts. This mirrors ``test_a_qagent_token_cannot_manage_the_hub``.

## Ownership

Every read resolves **own → shared → 404** (``services.project_service``). A
member never sees another member's project, config or knowledge, and its absence
is a 404 rather than a 403 — a 403 would confirm it exists.

## Test-account passwords

Encrypted at rest and returned in plaintext by exactly one route,
``GET /projects/{key}/config``, and only when ``config.owner_id == caller.id``
(INTEGRATION.md §3). A shared config, another member's config, and every list
response report ``hasPassword`` only. Nothing in this module logs an account.
"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import Field
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps_auth import require_principal, require_user
from app.models.knowledge import BUILD_TOTAL_STEPS, KNOWLEDGE_STATUSES, ProjectKnowledge
from app.models.project import Project
from app.models.user import User
from app.schemas import ApiModel
from app.services import (
    audit_service,
    knowledge_service,
    project_config_service,
    project_service,
)

router = APIRouter(prefix="/projects", tags=["projects"])


# ---------------------------------------------------------------- schemas
# Declared here rather than in ``app/schemas.py``: three slices are landing in
# parallel and the shared schema module is the one file they would all collide
# on. Same ``ApiModel`` base, so the wire stays camelCase either way.
class ProjectSummaryOut(ApiModel):
    """Card figures, so the list screen costs one request instead of 3N+1.

    Non-secret scalars only — deliberately **no test-account material of any
    kind, not even ``hasPassword``**. See ``list_projects``.
    """

    repo: str = ""
    repo_url: str = ""
    branch: str = ""
    repo_count: int = 0
    provider: str = ""
    knowledge_status: str = "not_indexed"
    knowledge_confidence: int = 0
    ticket_count: int = 0


class ProjectOut(ApiModel):
    id: int
    key: str
    name: str = ""
    shared: bool = False
    created_at: datetime | None = None
    updated_at: datetime | None = None
    #: Present on list and detail reads; absent on a write response.
    summary: ProjectSummaryOut | None = None


class ProjectIn(ApiModel):
    key: str
    name: str = ""
    #: Admin-only. A non-admin asking for a shared project gets their own.
    shared: bool = False


class ProjectRenameIn(ApiModel):
    name: str


class RepoIn(ApiModel):
    name: str
    repo_url: str = ""
    default_branch: str = ""
    #: Path on the AGENT host. Stored and echoed; never resolved by the hub.
    local_repo_path: str = ""
    default: bool = False


class EnvironmentIn(ApiModel):
    name: str = ""
    base_url: str = ""
    notes: str = ""


class TestAccountIn(ApiModel):
    role: str = ""
    username: str = ""
    #: Plaintext in, encrypted at rest. Blank keeps the stored secret.
    password: str = ""
    notes: str = ""


class TestAccountOut(ApiModel):
    role: str = ""
    username: str = ""
    notes: str = ""
    has_password: bool = False
    #: Present ONLY on an owner's own config read (INTEGRATION.md §3).
    password: str | None = None


class ProjectConfigOut(ApiModel):
    key: str
    name: str = ""
    work_item_connection_id: int | None = None
    repository_connection_id: int | None = None
    base_url: str = ""
    repos: list[dict] = Field(default_factory=list)
    environments: list[dict] = Field(default_factory=list)
    test_accounts: list[TestAccountOut] = Field(default_factory=list)
    extra: dict = Field(default_factory=dict)
    manual_auth: bool = False
    shared: bool = False
    #: When this configuration last changed (#147). The change signal for anyone
    #: mirroring it — poll this, or revalidate with `If-None-Match` against the
    #: `ETag` the same endpoint returns. `null` means never configured.
    updated_at: datetime | None = None


def _if_none_match(request: Request, etag: str) -> bool:
    """Does the caller already hold this exact representation? (#147)

    `If-None-Match` is a comma-separated **list**, and `*` matches anything that
    exists, so neither a bare string compare nor a substring test is correct.

    Comparison is weak: our validator is a `W/`-prefixed timestamp, and RFC 9110
    requires weak comparison for `If-None-Match` anyway — a strong compare would
    make every weak tag miss and quietly disable revalidation altogether, which
    looks exactly like it working (the responses are simply always 200).
    """
    header = request.headers.get("if-none-match")
    if not header:
        return False

    def weak(tag: str) -> str:
        tag = tag.strip()
        return tag[2:] if tag.startswith("W/") else tag

    candidates = [weak(t) for t in header.split(",") if t.strip()]
    return "*" in candidates or weak(etag) in candidates


class ProjectConfigIn(ApiModel):
    name: str | None = None
    work_item_connection_id: int | None = None
    repository_connection_id: int | None = None
    base_url: str | None = None
    repos: list[RepoIn] | None = None
    environments: list[EnvironmentIn] | None = None
    test_accounts: list[TestAccountIn] | None = None
    extra: dict | None = None
    manual_auth: bool | None = None
    shared: bool = False


class KnowledgeOut(ApiModel):
    id: int
    key: str
    project_key: str = ""
    name: str = ""
    provider: str = ""
    repo: str = ""
    framework: str = "Playwright"
    status: str = "not_indexed"
    confidence: int = 0
    version: str = "v1"
    needs_refresh: bool = False
    last_indexed: datetime | None = None
    knowledge: dict = Field(default_factory=dict)
    doc_path: str = ""
    last_error: str = ""
    shared: bool = False

    # ── Build progress (issue #68) ─────────────────────────────────────────
    # Extending the read the UI already polls, rather than adding a second
    # endpoint: the client needs the status and the progress together to decide
    # anything, and two calls could disagree with each other.
    #: One of ``knowledge.BUILD_STAGES``; "" when nothing is in flight.
    build_stage: str = ""
    #: 1-based ordinal of the stage; 0 when there is none.
    build_step: int = 0
    #: Total stages, so "3 of 5" needs no hard-coded 5 on the client.
    build_total_steps: int = BUILD_TOTAL_STEPS
    #: The live line. Scrubbed and length-bounded before it was stored.
    build_message: str = ""
    #: When the current (or last) build started — the elapsed clock.
    build_started_at: datetime | None = None
    #: This row says ``indexing`` but no worker is behind it — a build orphaned
    #: by a restarted container. The client offers a retry instead of spinning.
    build_orphaned: bool = False


class KnowledgeReportIn(ApiModel):
    """What an agent reports after a build it ran on its own host."""

    status: str | None = None
    knowledge: dict | None = None
    confidence: int | None = None
    #: Agent-host directory holding knowledge.md/.json. Opaque to the hub.
    doc_path: str | None = None
    last_error: str | None = None
    needs_refresh: bool | None = None
    name: str | None = None
    provider: str | None = None
    framework: str | None = None


class KnowledgeDiscoveryIn(ApiModel):
    """``PATCH`` body — routes/selectors observed against the live application."""

    routes: list[dict] = Field(default_factory=list)
    selectors: list[dict] = Field(default_factory=list)
    source: str = "exploration"


class KnowledgeMergeOut(ApiModel):
    merged: int = 0
    knowledge: KnowledgeOut


# ---------------------------------------------------------------- helpers
def _project_out(row: Project, summary: dict | None = None) -> ProjectOut:
    return ProjectOut(
        id=row.id,
        key=row.key,
        name=row.name or row.key,
        shared=row.owner_id is None,
        created_at=row.created_at,
        updated_at=row.updated_at,
        summary=ProjectSummaryOut(**summary) if summary is not None else None,
    )


def _knowledge_out(row: ProjectKnowledge) -> KnowledgeOut:
    return KnowledgeOut(
        id=row.id,
        key=row.key,
        project_key=row.project_key,
        name=row.name,
        provider=row.provider,
        repo=row.repo,
        framework=row.framework,
        status=row.status,
        confidence=row.confidence,
        version=row.version,
        needs_refresh=row.needs_refresh,
        last_indexed=row.last_indexed,
        knowledge=row.knowledge or {},
        doc_path=row.doc_path,
        last_error=row.last_error,
        shared=row.owner_id is None,
        build_stage=row.build_stage or "",
        build_step=row.build_step or 0,
        build_total_steps=BUILD_TOTAL_STEPS,
        build_message=row.build_message or "",
        build_started_at=row.build_started_at,
        build_orphaned=knowledge_service.is_orphaned(row),
    )


def _project_or_404(db: Session, key: str, user: User | None) -> Project:
    row = project_service.get_project(db, key, user)
    if row is None:
        raise HTTPException(status_code=404, detail=f"Project '{key}' not found")
    return row


# ---------------------------------------------------------------- projects
@router.get("", response_model=list[ProjectOut])
def list_projects(
    principal: User = Depends(require_principal), db: Session = Depends(get_db)
) -> list[ProjectOut]:
    """The project registry visible to the caller (INTEGRATION.md §3).

    Own rows plus the shared namespace, never another member's. Deliberately no
    test-account material of any kind, not even ``hasPassword`` — a list
    response is the easiest thing to log wholesale. ``summary`` carries only
    non-secret card figures, batch-loaded in three queries for the whole list.
    """
    rows = project_service.list_projects(db, principal)
    summaries = project_service.summaries_for(db, rows, principal)
    return [_project_out(p, summaries.get(p.key)) for p in rows]


@router.get("/{key}", response_model=ProjectOut)
def get_project(
    key: str, principal: User = Depends(require_principal), db: Session = Depends(get_db)
) -> ProjectOut:
    row = _project_or_404(db, key, principal)
    return _project_out(row, project_service.summaries_for(db, [row], principal).get(row.key))


@router.post("", response_model=ProjectOut, status_code=201)
def create_project(
    body: ProjectIn, user: User = Depends(require_user), db: Session = Depends(get_db)
) -> ProjectOut:
    """Register a project. Hub audience only — an agent does not create projects."""
    key = (body.key or "").strip()
    if not key:
        raise HTTPException(status_code=400, detail="key is required")
    row = project_service.upsert_project(
        db, key, name=(body.name or "").strip() or key, user=user, shared=body.shared
    )
    db.commit()
    db.refresh(row)
    audit_service.record(
        category="project",
        action="Created project",
        target=row.key,
        actor=user.email,
        actor_id=user.id,
        owner_id=row.owner_id,
        db=db,
    )
    return _project_out(row)


@router.patch("/{key}", response_model=ProjectOut)
def rename_project(
    key: str,
    body: ProjectRenameIn,
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
) -> ProjectOut:
    """Rename. Resolves own → shared, and 404s on a row the caller may not see."""
    row = _project_or_404(db, key, user)
    if row.owner_id is None and not _may_write_shared(user):
        raise HTTPException(status_code=403, detail="Only admins may edit shared projects")
    row.name = body.name
    db.commit()
    db.refresh(row)
    return _project_out(row)


def _may_write_shared(user: User | None) -> bool:
    from app.services.ownership import can_write_shared

    return can_write_shared(user)


@router.delete("/{key}", status_code=204, response_class=Response)
def delete_project(
    key: str,
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
) -> Response:
    """Delete a project and everything the hub owns about it. Hub audience only.

    Scoped like every other project read: own → shared → **404**. Another
    member's same-keyed project is invisible, so it is not found rather than
    forbidden — a 403 here would confirm it exists. A *shared* project resolves
    and then needs the admin rule, which is a real 403: the caller can see the
    row, they simply may not delete it.

    **Cascade.** ``project_config`` (including the encrypted test-account
    passwords), every ``project_knowledge`` row for the key, and the project's
    directories in the workspace volume — the shallow clone and the built
    knowledge artefacts. All pinned to the project's own namespace.

    **Tickets block the delete rather than being cascaded.** A ticket mirrors a
    real work item in Azure DevOps or Jira; deleting a batch of them as a side
    effect of tidying up the registry destroys more than was asked for, and the
    hub cannot put them back without the connection the project was bound to.
    Orphaning them is not on the table either. So this returns ``409`` naming
    the count, and ``DELETE /tickets/{external_id}`` is the explicit second
    step. See ``project_service.delete_project``.
    """
    row = _project_or_404(db, key, user)
    if row.owner_id is None and not _may_write_shared(user):
        raise HTTPException(
            status_code=403, detail="Only admins may delete shared projects"
        )

    shared = row.owner_id is None
    try:
        removed = project_service.delete_project(db, row)
    except project_service.ProjectHasTickets as exc:
        raise HTTPException(
            status_code=409,
            detail=(
                f"This project still mirrors {exc.count} work "
                f"item{'' if exc.count == 1 else 's'}. Delete them from Tickets "
                "first, then delete the project."
            ),
        ) from exc

    db.commit()
    audit_service.record(
        category="project",
        action="Deleted project",
        target=key,
        actor=user.email,
        actor_id=user.id,
        # Counts only — never a config field, never an account.
        meta=(
            f"{removed['configs']} config row(s), "
            f"{removed['knowledge']} knowledge row(s)"
        ),
        owner_id=None if shared else user.id,
        db=db,
    )
    return Response(status_code=204)


# ---------------------------------------------------------------- config
@router.get(
    "/{key}/config",
    response_model=ProjectConfigOut,
    # Declared, because a raw `Response` is invisible to the generated schema:
    # without this the contract advertises only 200, and a client generated from
    # it treats the 304 this endpoint deliberately returns as an unexpected
    # status. The header is documented for the same reason — it is the half of
    # the exchange the caller has to send back.
    responses={
        304: {
            "description": (
                "Not Modified — the `If-None-Match` validator still matches, so the "
                "configuration has not changed since it was issued. No body."
            ),
            "headers": {
                "ETag": {
                    "description": "Repeated so the next revalidation has a validator.",
                    "schema": {"type": "string"},
                }
            },
        }
    },
)
def get_project_config(
    key: str,
    response: Response,
    request: Request,
    principal: User = Depends(require_principal),
    db: Session = Depends(get_db),
) -> ProjectConfigOut | Response:
    """Full project configuration (INTEGRATION.md §3).

    **Test-account passwords are returned only to the owning user.** ``reveal``
    is true exactly when the resolved row is owned by the caller; a shared row
    (``owner_id IS NULL``) is owned by nobody, so its accounts stay masked even
    for an admin — a shared credential that everyone can read is a credential
    that has left the hub.

    Conditional (#147). Agents mirror this config and render it read-only, so
    without a change signal they cannot tell a stale copy from a current one and
    their screens quietly lie. Two are offered, from the same value:
    ``updatedAt`` in the body for anyone who would rather poll a field, and an
    ``ETag`` for anyone who would rather revalidate and get ``304`` with no body.
    """
    _project_or_404(db, key, principal)
    row = project_config_service.get_config(db, key, principal)
    reveal = row is not None and row.owner_id is not None and row.owner_id == principal.id

    etag = project_config_service.config_etag(row, reveal=reveal)
    # Private, not public: the body varies by caller (see `reveal`), so a shared
    # cache must never serve one user's copy to another. `must-revalidate` keeps
    # a client from treating a stored copy as fresh without asking.
    response.headers["Cache-Control"] = "private, no-cache, must-revalidate"
    response.headers["ETag"] = etag

    if _if_none_match(request, etag):
        # 304 carries no body, but the validator has to be repeated or the client
        # has nothing to revalidate against next time.
        return Response(
            status_code=304,
            headers={"ETag": etag, "Cache-Control": "private, no-cache, must-revalidate"},
        )

    return ProjectConfigOut(**project_config_service.config_payload(row, key, reveal=reveal))


@router.put("/{key}/config", response_model=ProjectConfigOut)
def save_project_config(
    key: str,
    body: ProjectConfigIn,
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
) -> ProjectConfigOut:
    """Create or update a project's configuration. Hub audience only.

    Passwords arrive in plaintext and are encrypted before they are stored; a
    blank password preserves the stored one, so saving the masked form back is
    safe. The response re-reads through the same masking rule as the GET.
    """
    _project_or_404(db, key, user)
    patch = body.model_dump(exclude_unset=True, exclude={"shared"})
    if body.repos is not None:
        patch["repos"] = [r.model_dump() for r in body.repos]
    if body.environments is not None:
        patch["environments"] = [e.model_dump() for e in body.environments]
    if body.test_accounts is not None:
        patch["test_accounts"] = [a.model_dump() for a in body.test_accounts]
    row = project_config_service.upsert_config(db, key, patch, user=user, shared=body.shared)
    db.commit()
    db.refresh(row)
    audit_service.record(
        category="project",
        action="Saved project configuration",
        target=row.key,
        actor=user.email,
        actor_id=user.id,
        # Counts only — never an account, never a password.
        meta=f"{len(row.test_accounts or [])} test account(s), {len(row.repos or [])} repo(s)",
        owner_id=row.owner_id,
        db=db,
    )
    reveal = row.owner_id is not None and row.owner_id == user.id
    return ProjectConfigOut(**project_config_service.config_payload(row, key, reveal=reveal))


# ---------------------------------------------------------------- knowledge
@router.get("/{key}/knowledge", response_model=KnowledgeOut)
def get_project_knowledge(
    key: str, principal: User = Depends(require_principal), db: Session = Depends(get_db)
) -> KnowledgeOut:
    """Project-level knowledge (INTEGRATION.md §3)."""
    row = knowledge_service.get_knowledge(db, key, "", principal)
    if row is None:
        raise HTTPException(status_code=404, detail=f"No knowledge base for project '{key}'")
    return _knowledge_out(row)


@router.get("/{key}/repos/{repo}/knowledge", response_model=KnowledgeOut)
def get_repo_knowledge(
    key: str,
    repo: str,
    principal: User = Depends(require_principal),
    db: Session = Depends(get_db),
) -> KnowledgeOut:
    """Per-repository knowledge, falling back to the project-level row."""
    row = knowledge_service.get_knowledge(db, key, repo, principal)
    if row is None:
        raise HTTPException(status_code=404, detail=f"No knowledge base for repo '{repo}'")
    return _knowledge_out(row)


@router.put("/{key}/repos/{repo}/knowledge", response_model=KnowledgeOut)
def report_repo_knowledge(
    key: str,
    repo: str,
    body: KnowledgeReportIn,
    principal: User = Depends(require_principal),
    db: Session = Depends(get_db),
) -> KnowledgeOut:
    """Record a build outcome the **agent** produced on its own host.

    This stays after ADR 0007. The hub having become *a* builder does not make
    it the only one: QAgent already builds its own knowledge, and an agent that
    did the work should be able to report it — status, the knowledge blob,
    confidence, and the agent-host ``docPath`` of its own artifacts, which the
    hub stores and never resolves.

    Agent audience is accepted (this is an agent's job). Ownership follows
    ``knowledge_service.write_target``: the caller's own row, the shared row when
    the caller is an admin, else a new row owned by the caller.
    """
    if body.status is not None and body.status not in KNOWLEDGE_STATUSES:
        raise HTTPException(status_code=400, detail=f"Unknown status '{body.status}'")
    row = knowledge_service.write_target(db, key, repo, principal)
    knowledge_service.apply_metadata(row, body.model_dump(exclude_unset=True))
    knowledge_service.apply_build_result(
        row,
        knowledge=body.knowledge,
        confidence=body.confidence,
        status=body.status,
        doc_path=body.doc_path,
        last_error=body.last_error,
        needs_refresh=body.needs_refresh,
    )
    db.commit()
    db.refresh(row)
    return _knowledge_out(row)


@router.post(
    "/{key}/repos/{repo}/knowledge/build", response_model=KnowledgeOut, status_code=202
)
def build_repo_knowledge(
    key: str,
    repo: str,
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
) -> KnowledgeOut:
    """**Build** a knowledge base on the hub (ADR 0007). Hub audience only.

    The hub clones the repository into the caller's workspace scope, runs
    ``project-bootstrap`` through the Claude CLI against that clone, writes
    ``knowledge.md``/``knowledge.json`` and updates the row. That is minutes of
    work, so the endpoint does none of it: it moves the row to ``indexing``,
    commits, hands off to a background worker and returns ``202`` immediately.

    **What the client does next.** Poll ``GET /projects/{key}/repos/{repo}/knowledge``
    until ``status`` leaves ``indexing``. ``indexed`` carries the new blob,
    confidence and version; ``error`` carries ``lastError``, which is written for
    a human and is safe to display verbatim (never a token — see
    ``services/repo_service.py``).

    **Requesting twice is safe.** A second call while a build is in flight
    returns the same ``indexing`` row without starting anything; the response is
    identical, which is the point. Builds beyond
    ``EMEHUB_KNOWLEDGE_BUILD_CONCURRENCY`` queue rather than run.

    Ownership follows ``knowledge_service.write_target`` — the caller's own row,
    the shared row when they are an admin, else a new row owned by them. The
    clone, the artefacts and the Claude spend all land in that same scope.
    """
    _project_or_404(db, key, user)
    row, started = knowledge_service.request_build(db, key, repo, user)
    if started:
        audit_service.record(
            category="knowledge",
            action="Requested a knowledge build",
            target=row.key,
            actor=user.email,
            actor_id=user.id,
            owner_id=row.owner_id,
            db=db,
        )
    return _knowledge_out(row)


@router.patch("/{key}/repos/{repo}/knowledge", response_model=KnowledgeMergeOut)
def contribute_repo_knowledge(
    key: str,
    repo: str,
    body: KnowledgeDiscoveryIn,
    principal: User = Depends(require_principal),
    db: Session = Depends(get_db),
) -> KnowledgeMergeOut:
    """**The write path** (INTEGRATION.md §3): contribute discovered entries.

    An agent that drove the live application observed real routes and selectors.
    They are merged with the no-clobber rule in
    ``knowledge_service.merge_discovery``: **an existing entry carrying
    ``verified_at_runtime`` is never overwritten**, an unverified entry is
    upgraded in place, and anything new is appended.

    The row is created on demand when the caller has none. Discovery is the only
    way knowledge reaches a hub that cannot build one itself, so dropping a
    contribution because nothing has been indexed yet would make the endpoint
    useless; the row simply stays ``not_indexed`` until an agent reports a build.
    """
    row = knowledge_service.write_target(db, key, repo, principal)
    merged = knowledge_service.merge_discovery(
        row, {"routes": body.routes, "selectors": body.selectors}, source=body.source
    )
    db.commit()
    db.refresh(row)
    if merged:
        audit_service.record(
            category="knowledge",
            action="Contributed runtime-verified knowledge",
            actor_type="agent",
            actor=principal.email,
            actor_id=principal.id,
            source=getattr(principal, "_aud", None),
            target=row.key,
            meta=f"{merged} entr{'y' if merged == 1 else 'ies'} from {body.source}",
            owner_id=row.owner_id,
            db=db,
        )
    return KnowledgeMergeOut(merged=merged, knowledge=_knowledge_out(row))
