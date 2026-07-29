"""Project knowledge — the build, the metadata persistence and the discovery merge.

## The hub builds (ADR 0007)

This module used to be metadata-only, because the hub owned no workspace, ran no
Claude CLI and cloned no repositories. [ADR 0007](../../../docs/adr/0007-knowledge-builds-run-on-the-hub.md)
reversed that: the hub clones into a per-owner workspace, runs
``project-bootstrap`` through the Claude CLI against the clone, writes
``knowledge.md`` / ``knowledge.json`` and updates the row itself.

The build half is :func:`start_build` → :func:`_run_build` →
:func:`build_knowledge_payload` / :func:`write_knowledge_files`, and it is
governed by three rules that exist because a build is minutes long, spends money
and runs untrusted-ish input through a subprocess:

**Backgrounded, and ``indexing`` is committed first.** The endpoint sets the row
to ``indexing`` and commits *before* the worker starts, so the UI reflects the
state immediately and a second request finds a build already in flight rather
than starting a duplicate.

**Bounded concurrency.** :data:`_semaphore` caps concurrent builds process-wide
at ``settings.knowledge_build_concurrency``. Over the cap, a worker waits with
its row still ``indexing`` — queued, never dropped, and never able to let one
member's twenty repositories starve everyone else's one.

**Failure is a status, not an exception.** Every failure mode — no clone URL, no
repository connection, a clone that fails, a missing credential, a CLI timeout,
non-JSON output — lands the row in ``error`` with a ``last_error`` a human can
act on. Nothing propagates out of the worker thread, and nothing that reaches
``last_error`` has been near a PAT (``repo_service`` scrubs; see there).

``PUT .../knowledge`` **stays** (:func:`apply_build_result`). QAgent builds its
own knowledge and reports it, and the hub becoming *a* builder does not make it
the only one.

## What IS still here from before

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

import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any

from sqlalchemy.orm import Session

from app.config import settings
from app.db import utcnow
from app.logging import logger
from app.models.knowledge import (
    KNOWLEDGE_STATUSES,
    STATUS_ERROR,
    STATUS_INDEXED,
    STATUS_INDEXING,
    STATUS_NOT_INDEXED,
    ProjectKnowledge,
    compose_key,
)
from app.models.user import User
from app.services import project_service
from app.services.ownership import stamp_owner

if TYPE_CHECKING:  # pragma: no cover
    from app.models.project_config import ProjectConfig


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


# ------------------------------------------------------------------- build
#
# Everything below this line arrived with ADR 0007. Above it is unchanged: the
# hub still records what an agent reports, it has simply also become a builder.

#: Guards :data:`_building`. Held only for the set operations, never across the
#: build itself.
_BUILD_LOCK = threading.Lock()

#: ``ProjectKnowledge.id`` of every build in flight in this process. Keyed by id
#: rather than by row key because the same key exists once per member and once
#: shared — keying by string would let one member's build block another's.
_building: set[int] = set()

_SEMAPHORE_LOCK = threading.Lock()
_semaphore: threading.BoundedSemaphore | None = None
_semaphore_capacity = 0


def _build_semaphore() -> threading.BoundedSemaphore:
    """The process-wide concurrency cap, built lazily from settings.

    Rebuilt when ``knowledge_build_concurrency`` changes so a test (or a config
    reload) is not stuck with the first value the process ever saw. A capacity
    below 1 is clamped: a cap of zero would silently disable building.
    """
    global _semaphore, _semaphore_capacity
    capacity = max(1, int(settings.knowledge_build_concurrency or 1))
    with _SEMAPHORE_LOCK:
        if _semaphore is None or _semaphore_capacity != capacity:
            _semaphore = threading.BoundedSemaphore(capacity)
            _semaphore_capacity = capacity
        return _semaphore


def is_building(row_id: int) -> bool:
    """True when a build for this row is already in flight in this process."""
    with _BUILD_LOCK:
        return row_id in _building


def start_build(row_id: int) -> bool:
    """Start a background build for ``row_id``; ``False`` if one is already running.

    The check and the claim happen under one lock, so two requests racing on the
    same row cannot both win.

    The guard is deliberately **in-process**, not the ``indexing`` column. A row
    left ``indexing`` by a container that died mid-build is not evidence that a
    build is running — it is evidence that one is not — and a status-only guard
    would wedge that row permanently. Asking again after a restart therefore
    starts a fresh build, which is the behaviour a user pressing the button
    twenty minutes later expects.
    """
    with _BUILD_LOCK:
        if row_id in _building:
            return False
        _building.add(row_id)
    threading.Thread(
        target=_run_build, args=(row_id,), name=f"knowledge-build-{row_id}", daemon=True
    ).start()
    return True


def _run_build(row_id: int) -> None:
    """Worker body. Waits for a slot, builds, and can never raise.

    The semaphore is acquired *before* the session is opened so a queued build
    holds no database connection while it waits.
    """
    from app import db as db_module

    semaphore = _build_semaphore()
    semaphore.acquire()
    try:
        db = db_module.SessionLocal()
        try:
            _build(db, row_id)
        except Exception as exc:  # noqa: BLE001 - a build failure is a row status
            _record_failure(db, row_id, exc)
        finally:
            db.close()
    finally:
        semaphore.release()
        with _BUILD_LOCK:
            _building.discard(row_id)


def _record_failure(db: Session, row_id: int, exc: BaseException) -> None:
    """Land the failure on the row as ``error`` + ``last_error``. Never raises.

    ``repo_service.redact`` runs over the message even though the clone path
    already scrubbed its own: this is the last point before the text becomes a
    database column and an API response, and a defence that only works when
    every upstream caller remembered is not a defence.
    """
    from app.services.repo_service import redact

    message = redact(str(exc) or exc.__class__.__name__)[:1000]
    try:
        db.rollback()
        row = db.get(ProjectKnowledge, row_id)
        if row is not None:
            row.status = STATUS_ERROR
            row.last_error = message
            db.commit()
    except Exception as inner:  # noqa: BLE001
        logger.error("Could not record a knowledge build failure: %s", inner)
    logger.error("Knowledge build %s failed: %s", row_id, message)


def _build(db: Session, row_id: int) -> None:
    """One build, start to finish. Raises on any failure; the worker records it."""
    from app.services import audit_service, project_config_service, repo_service

    row = db.get(ProjectKnowledge, row_id)
    if row is None:
        logger.warning("Knowledge build %s: the row disappeared before it started", row_id)
        return

    project_key = row.project_key or row.key
    # Pinned to the row's own namespace, never resolved own → shared: a shared
    # build must read the shared config, not a member's same-keyed copy.
    config = project_config_service.get_config_for_owner(db, project_key, row.owner_id)

    clone = repo_service.ensure_clone(
        db,
        project_key=project_key,
        repo_name=row.repo,
        repo_url=_clone_url(config, row),
        owner_id=row.owner_id,
        bound_connection_id=getattr(config, "repository_connection_id", None),
    )
    payload = build_knowledge_payload(
        db,
        name=row.name or project_key,
        provider=row.provider,
        repo=row.repo,
        framework=row.framework,
        owner_id=row.owner_id,
        config=config,
        repo_path=clone,
    )
    apply_build(row, payload, config=config)
    db.commit()
    audit_service.record(
        category="knowledge",
        actor_type="system",
        action="Built project knowledge base",
        target=row.key,
        meta=f"{row.version} · {row.confidence}% confidence",
        owner_id=row.owner_id,
        db=db,
    )


def _clone_url(config: "ProjectConfig | None", row: ProjectKnowledge) -> str:
    """The ``repo_url`` for the row's repository, from the project's config.

    ``local_repo_path`` is deliberately ignored — it names a directory on an
    *agent* host (``project_config_service.REPO_FIELDS``) and resolving it inside
    the API container would either fail or, worse, traverse something unrelated
    that happens to sit at that path.
    """
    from app.services import project_config_service

    repos = project_config_service.get_repos(config)
    if row.repo:
        entry = next((r for r in repos if r.get("name") == row.repo), None)
        if entry is None:
            raise ValueError(
                f"'{row.repo}' is not one of this project's repositories. Add it "
                "under Project settings › Repositories, then build again."
            )
    else:
        entry = project_config_service.default_repo(config)
        if entry is None:
            raise ValueError(
                "This project has no repositories configured. Add one under "
                "Project settings › Repositories, then build again."
            )
    return (entry.get("repo_url") or "").strip()


# --------------------------------------------------------------- the prompt
def _config_hints(config: "ProjectConfig | None") -> str:
    """The user-authored configuration, rendered as grounding facts.

    Roles and usernames only. **A test-account password is never written into a
    prompt** — it is encrypted at rest precisely so it does not travel, and a
    prompt is the least controllable place a secret can end up.

    QAgent's version also advertises ``local_repo_path``; the hub's does not,
    because the hub runs the CLI *inside* the clone (see
    :func:`build_knowledge_payload`) and pointing Claude at an agent-host path
    it cannot open would only invite it to invent one.
    """
    if config is None:
        return "No project configuration has been provided yet.\n"
    lines: list[str] = []
    if config.base_url:
        lines.append(f"- Application base URL: {config.base_url}")
    for env in config.environments or []:
        name, url = env.get("name", ""), env.get("base_url", "")
        if name or url:
            lines.append(f"- Environment '{name}': {url}")
    roles = [a.get("role", "") for a in (config.test_accounts or []) if a.get("role")]
    if roles:
        lines.append(f"- Configured test-account roles: {', '.join(roles)}")
    if not lines:
        return "No project configuration has been provided yet.\n"
    return "\n".join(lines) + "\n"


def _build_prompt(
    name: str, provider: str, repo: str, framework: str, config: "ProjectConfig | None"
) -> str:
    """The bootstrap prompt. Kept shape-identical to QAgent's so a knowledge base
    built by either side answers the same keys."""
    return (
        "Build a Project Knowledge Base for this software project so a QA "
        "automation agent can generate runnable Playwright tests with NO manual "
        "placeholders. Discover concrete, reusable facts.\n\n"
        "The repository is checked out in your working directory — traverse it "
        "with your file tools to discover real routes, data-testids/selectors, "
        "page objects, fixtures and the authentication flow.\n\n"
        f"Project name: {name}\n"
        f"Provider: {provider or 'unknown'}\n"
        f"Repository: {repo or 'unknown'}\n"
        f"Automation framework: {framework or 'Playwright'}\n\n"
        "Known project configuration (treat as authoritative):\n"
        f"{_config_hints(config)}\n"
        "Return a JSON object with EXACTLY these keys:\n"
        '{"branch": string, "stack": string[], "architecture": string, '
        '"domain": string, "locator": string, "base_url": string, '
        '"routes": [{"path": string, "description": string, "auth_required": boolean}], '
        '"selectors": [{"screen": string, "element": string, "selector": string}], '
        '"auth": {"login_flow": string, "login_url": string, "storage_state": string}, '
        '"environments": [{"name": string, "base_url": string, "notes": string}], '
        '"business_entities": string[], "assets": number, "pageObjects": number, '
        '"page_object_names": string[], "fixtures": number, "fixture_names": string[], '
        '"utilities": string[], "confidence": number (0-100)}\n'
        "- base_url: the primary application URL (use the configured one if given).\n"
        "- routes: real application routes/URL patterns a test would navigate to.\n"
        "- selectors: real, stable selectors (prefer data-testid / role) found in the code.\n"
        "- auth: how a test logs in — flow summary, the login URL, and any storageState path.\n"
        "- architecture/domain: 1-2 sentences each.\n"
        "- assets/pageObjects/fixtures: best-estimate COUNTS of existing Playwright assets.\n"
        "- page_object_names/fixture_names: the actual names of reusable assets to reuse.\n"
        "- confidence: how confident this knowledge base is (0-100). "
        "Lower it for anything guessed."
    )


def build_knowledge_payload(
    db: Session,
    *,
    name: str,
    provider: str,
    repo: str,
    framework: str,
    owner_id: int | None,
    config: "ProjectConfig | None" = None,
    repo_path: str | Path | None = None,
    timeout: int | None = None,
) -> dict[str, Any]:
    """Run ``project-bootstrap`` against the clone and normalise the result.

    ``owner_id`` is the *row's* owner, so the call resolves that member's own (or
    the shared) Claude credential and the usage row is stamped with whoever
    actually paid. ``repo_path`` becomes the CLI's working directory — that is
    what turns inferred structure into discovered fact.

    Every key is defaulted, so a model that omits one produces a thin knowledge
    base rather than a ``KeyError`` that fails an otherwise fine build.
    """
    from app.services.claude_cli import run_json
    from app.services.skills import PROJECT_BOOTSTRAP

    raw = run_json(
        _build_prompt(name, provider, repo, framework, config),
        db=db,
        owner_id=owner_id,
        skill=PROJECT_BOOTSTRAP,
        include_template=True,
        label=f"Build knowledge: {name}",
        cwd=repo_path,
        timeout=timeout or settings.claude_bootstrap_timeout_s,
    )
    data = raw if isinstance(raw, dict) else {}
    try:
        confidence = int(data.get("confidence", 80) or 0)
    except (TypeError, ValueError):
        confidence = 0
    return {
        "knowledge": {
            "branch": data.get("branch", "main"),
            "stack": data.get("stack") or [],
            "architecture": data.get("architecture", ""),
            "domain": data.get("domain", ""),
            "locator": data.get("locator", ""),
            "base_url": data.get("base_url", ""),
            "routes": data.get("routes") or [],
            "selectors": data.get("selectors") or [],
            "auth": data.get("auth") or {},
            "environments": data.get("environments") or [],
            "business_entities": data.get("business_entities") or [],
            "assets": _as_int(data.get("assets")),
            "pageObjects": _as_int(data.get("pageObjects")),
            "page_object_names": data.get("page_object_names") or [],
            "fixtures": _as_int(data.get("fixtures")),
            "fixture_names": data.get("fixture_names") or [],
            "utilities": data.get("utilities") or [],
        },
        "confidence": max(0, min(100, confidence)),
    }


def _as_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def apply_build(
    row: ProjectKnowledge, payload: dict[str, Any], *, config: "ProjectConfig | None" = None
) -> None:
    """Persist a hub-run build onto ``row``, artefacts included. Caller commits.

    The metadata half is :func:`apply_build_result` — the same version, timestamp
    and error-clearing semantics an agent's report gets, so a row cannot tell you
    which side built it except by ``doc_path``. The difference is that here the
    hub *wrote* those artefacts, so ``doc_path`` is a hub workspace path it can
    resolve, rather than the opaque agent-host string a report carries.
    """
    apply_build_result(
        row,
        knowledge=payload["knowledge"],
        confidence=payload["confidence"],
        status=STATUS_INDEXED,
    )
    row.doc_path = str(write_knowledge_files(row, config))


def write_knowledge_files(
    row: ProjectKnowledge, config: "ProjectConfig | None" = None
) -> Path:
    """Emit ``knowledge.json`` + ``knowledge.md`` under the row owner's scope.

    ``project-bootstrap``'s contract is to persist the knowledge base as files
    that downstream skills read, so the row is mirrored into them and merged with
    the user-authored configuration to make one consistent project context.

    **Test-account passwords are never written.** Roles, usernames and notes
    only — the same rule ``_config_hints`` applies to the prompt. Returns the
    directory.
    """
    from app.services.workspace_scope import scoped_knowledge_dir, slug

    kn = row.knowledge or {}
    out_dir = scoped_knowledge_dir(row.owner_id) / slug(row.project_key or row.key)
    if row.repo:
        out_dir = out_dir / slug(row.repo)
    out_dir.mkdir(parents=True, exist_ok=True)

    base_url = (config.base_url if config and config.base_url else "") or kn.get("base_url", "")
    environments = (
        config.environments if config and config.environments else None
    ) or kn.get("environments", [])
    accounts = (
        [
            {
                "role": a.get("role", ""),
                "username": a.get("username", ""),
                "notes": a.get("notes", ""),
            }
            for a in (config.test_accounts or [])
        ]
        if config
        else []
    )

    document = {
        "project_name": row.name,
        "repository": row.repo,
        "branch": kn.get("branch", "main"),
        "automation": row.framework,
        "stack": kn.get("stack", []),
        "architecture": kn.get("architecture", ""),
        "business_domain": kn.get("domain", ""),
        "business_entities": kn.get("business_entities", []),
        "base_url": base_url,
        "locator_strategy": kn.get("locator", ""),
        "routes": kn.get("routes", []),
        "selectors": kn.get("selectors", []),
        "auth": kn.get("auth", {}),
        "environments": environments,
        "test_accounts": accounts,  # roles/usernames only — never a password
        "existing_assets": {
            "spec_files": kn.get("assets", 0),
            "page_objects": kn.get("pageObjects", 0),
            "page_object_names": kn.get("page_object_names", []),
            "fixtures": kn.get("fixtures", 0),
            "fixture_names": kn.get("fixture_names", []),
        },
        "reusable_utilities": kn.get("utilities", []),
        "confidence": row.confidence,
        "version": row.version,
        "indexed_at": row.last_indexed.isoformat() if row.last_indexed else None,
        "built_by": "emehub",
    }
    (out_dir / "knowledge.json").write_text(
        json.dumps(document, indent=2), encoding="utf-8"
    )
    (out_dir / "knowledge.md").write_text(
        _knowledge_markdown(row, kn, base_url, environments, accounts), encoding="utf-8"
    )
    return out_dir


def _knowledge_markdown(
    row: ProjectKnowledge,
    kn: dict,
    base_url: str,
    environments: list,
    accounts: list[dict],
) -> str:
    """The human-readable half of the artefact pair."""
    stack = ", ".join(kn.get("stack", [])) or "—"
    routes = "\n".join(
        f"- `{r.get('path', '')}` — {r.get('description', '')}"
        f"{' (auth required)' if r.get('auth_required') else ''}"
        for r in kn.get("routes", [])
    ) or "- _none discovered_"
    selectors = "\n".join(
        f"- {s.get('screen', '')}: {s.get('element', '')} → `{s.get('selector', '')}`"
        for s in kn.get("selectors", [])
    ) or "- _none discovered_"
    envs = "\n".join(
        f"- **{e.get('name', '')}**: {e.get('base_url', '')} {e.get('notes', '')}".rstrip()
        for e in environments
    ) or "- _none configured_"
    accounts_md = "\n".join(
        f"- **{a['role'] or 'account'}**: `{a['username']}` "
        f"(password stored encrypted in EmeHub) {a['notes']}".rstrip()
        for a in accounts
    ) or "- _none configured_"
    utilities = "\n".join(f"- `{u}`" for u in kn.get("utilities", [])) or "- _none discovered_"
    auth = kn.get("auth", {}) or {}

    return f"""# Project Knowledge Base — {row.name}

- **Repository:** {row.repo or "—"}
- **Branch:** {kn.get("branch", "main")}
- **Automation framework:** {row.framework}
- **Base URL:** {base_url or "—"}
- **Confidence:** {row.confidence}%  ·  **Version:** {row.version}
- **Built by:** EmeHub

## Technology stack
{stack}

## Application architecture
{kn.get("architecture", "—")}

## Business domain
{kn.get("domain", "—")}

## Business entities
{", ".join(kn.get("business_entities", [])) or "—"}

## Locator strategy
{kn.get("locator", "—")}

## Application routes
{routes}

## Known selectors
{selectors}

## Authentication
- **Login flow:** {auth.get("login_flow", "—")}
- **Login URL:** {auth.get("login_url", "—")}
- **storageState:** {auth.get("storage_state", "—")}

## Environments
{envs}

## Test accounts
{accounts_md}

## Existing Playwright assets
- Spec files: {kn.get("assets", 0)}
- Page objects: {kn.get("pageObjects", 0)} {", ".join(kn.get("page_object_names", []))}
- Shared fixtures: {kn.get("fixtures", 0)} {", ".join(kn.get("fixture_names", []))}

## Reusable test utilities
{utilities}

## AI Context Summary
{row.name} ({stack}) at base URL {base_url or "(unset)"}. {kn.get("architecture", "")}
Domain: {kn.get("domain", "")} Prefer the locator strategy above and the listed routes,
selectors, auth flow and reusable assets. Test-account credentials are supplied by EmeHub's
encrypted store — reference them by role, never by value.
"""


def request_build(
    db: Session, project_key: str, repo: str, user: User
) -> tuple[ProjectKnowledge, bool]:
    """Move the row to ``indexing``, commit, then start the worker.

    Returns ``(row, started)``. ``started`` is ``False`` when a build for this
    row was already in flight — the caller still answers with the ``indexing``
    row, because from the requester's point of view the outcome is identical:
    a build is running and the status is the thing to poll.

    The commit happens **before** :func:`start_build` deliberately. If it did
    not, the worker could open its own session, read a row that is still
    ``not_indexed``, and race the request transaction that was about to say
    otherwise.
    """
    row = write_target(db, project_key, repo, user)
    if row.id is not None and is_building(row.id):
        return row, False
    row.status = STATUS_INDEXING
    row.last_error = ""
    db.commit()
    db.refresh(row)
    return row, start_build(row.id)
