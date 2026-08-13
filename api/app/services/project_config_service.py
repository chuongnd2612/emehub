"""Project configuration — persistence, encryption and serialisation.

Ported from QAgent's ``services/project_config_service.py``, **persistence half
only**. QAgent's other half resolves a full project *context* for a run (ticket →
work-item connection → project key → decrypted accounts → knowledge blob) and
manages ``storageState.json`` files under a per-user workspace. Neither belongs
here:

* the context resolution needs the tickets and connections tables and is a
  read the agent composes for itself from the endpoints in INTEGRATION.md §3;
* ``auth_path`` / ``session_path`` / ``clear_auth`` are pure filesystem, and
  **the hub owns no workspace filesystem** (ROADMAP.md Phase 4). See the
  *filesystem seams* note at the bottom of this module.

## Test-account passwords

Stored encrypted through :mod:`app.crypto` and returned in plaintext by exactly
one function, :func:`config_payload` with ``reveal=True``, which the router calls
only when the caller **owns** the row (INTEGRATION.md §3: "Test-account passwords
are returned only to the owning user"). Everything else — the list endpoint, a
shared row, another member — gets ``hasPassword: bool`` and nothing more.

Never log the output of a reveal. There is no logging in this module at all, on
purpose.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app import crypto
from app.models.project_config import ProjectConfig
from app.models.user import User
from app.services import project_service
from app.services.ownership import stamp_owner

#: Keys of a ``repos[]`` entry the hub stores. ``local_repo_path`` is an
#: agent-host path: stored, echoed, never resolved here.
REPO_FIELDS = ("name", "repo_url", "default_branch", "local_repo_path", "default")


# --------------------------------------------------------------- persistence
def get_config(db: Session, key: str, user: User | None) -> ProjectConfig | None:
    """The config visible to ``user`` for ``key`` — own → shared → ``None``."""
    return project_service.own_then_shared(db, ProjectConfig, user, ProjectConfig.key == key)


def get_config_for_owner(db: Session, key: str, owner_id: int | None) -> ProjectConfig | None:
    """The config in one specific namespace. Writes use this — never a fallback,
    or a member's save would silently edit the shared row."""
    return project_service.for_owner(db, ProjectConfig, owner_id, ProjectConfig.key == key)


def upsert_config(
    db: Session, key: str, patch: dict[str, Any], *, user: User | None, shared: bool = False
) -> ProjectConfig:
    """Create or update a project's config from a partial patch. Caller commits.

    Test-account passwords arrive in plaintext and are encrypted before they
    touch the row. A blank/absent password on an account **preserves** the stored
    ciphertext for the same ``(role, username)``, so a UI that round-trips the
    masked form cannot wipe the secret.
    """
    owner_id = project_service.write_target_owner(user, shared=shared)
    row = get_config_for_owner(db, key, owner_id)
    if row is None:
        row = ProjectConfig(key=key, name=patch.get("name") or key)
        row.owner_id = owner_id
        if owner_id is not None:
            stamp_owner(row, user)
        db.add(row)
    _apply_patch(row, patch)
    return row


def _apply_patch(row: ProjectConfig, patch: dict[str, Any]) -> None:
    """Apply a partial patch onto ``row`` in place."""
    if patch.get("name"):
        row.name = patch["name"]
    # Present-but-null clears a binding, so membership is what matters here.
    if "work_item_connection_id" in patch:
        row.work_item_connection_id = patch["work_item_connection_id"]
    if "repository_connection_id" in patch:
        row.repository_connection_id = patch["repository_connection_id"]
    if patch.get("base_url") is not None:
        row.base_url = str(patch["base_url"]).strip()
    if patch.get("repos") is not None:
        row.repos = normalize_repos(patch["repos"])
    if patch.get("environments") is not None:
        row.environments = patch["environments"]
    if patch.get("extra") is not None:
        row.extra = patch["extra"]
    if patch.get("test_accounts") is not None:
        row.test_accounts = _encrypt_accounts(patch["test_accounts"], row.test_accounts or [])
    if patch.get("manual_auth") is not None:
        row.manual_auth = bool(patch["manual_auth"])


def normalize_repos(incoming: list[dict]) -> list[dict]:
    """Clean a submitted repo list; ensure exactly one repo is flagged default."""
    out: list[dict] = []
    seen_default = False
    for repo in incoming or []:
        name = (repo.get("name") or "").strip()
        if not name:
            continue
        is_default = bool(repo.get("default")) and not seen_default
        seen_default = seen_default or is_default
        out.append(
            {
                "name": name,
                "repo_url": (repo.get("repo_url") or "").strip(),
                "default_branch": (repo.get("default_branch") or "").strip(),
                # Agent-host path. Stored verbatim; the hub never touches it.
                "local_repo_path": (repo.get("local_repo_path") or "").strip(),
                "default": is_default,
            }
        )
    if out and not any(r["default"] for r in out):
        out[0]["default"] = True
    return out


def get_repos(config: ProjectConfig | None) -> list[dict]:
    return list(config.repos or []) if config is not None else []


def default_repo(config: ProjectConfig | None) -> dict | None:
    """The repo automation targets by default (flagged ``default``, else first)."""
    repos = get_repos(config)
    if not repos:
        return None
    return next((r for r in repos if r.get("default")), repos[0])


def has_repo(config: ProjectConfig | None, repo: str) -> bool:
    return any(r.get("name") == repo for r in get_repos(config))


# --------------------------------------------------------------- encryption
def _encrypt_accounts(incoming: list[dict], existing: list[dict]) -> list[dict]:
    """Encrypt plaintext passwords; keep the stored ciphertext when input is blank."""
    prior: dict[tuple[str, str], str] = {
        (a.get("role", ""), a.get("username", "")): a.get("password", "") for a in existing
    }
    out: list[dict] = []
    for account in incoming or []:
        role = account.get("role", "") or ""
        username = account.get("username", "") or ""
        password = account.get("password") or ""
        if password:
            stored = crypto.encrypt(password)
        else:
            # Already an `enc::v1:` envelope (or empty) — never re-encrypted.
            stored = prior.get((role, username), "")
        out.append(
            {
                "role": role,
                "username": username,
                "password": stored,
                "notes": account.get("notes", "") or "",
            }
        )
    return out


def _account_payload(account: dict, *, reveal: bool) -> dict[str, Any]:
    """One test account on the wire.

    ``reveal=False`` — the default everywhere except an owner's own detail read —
    reports only *whether* a password exists. ``reveal=True`` decrypts. A value
    that fails to authenticate under the current key decrypts to ``None`` and is
    reported as an empty string: unavailable, never the raw ciphertext.
    """
    stored = account.get("password") or ""
    payload = {
        "role": account.get("role", ""),
        "username": account.get("username", ""),
        "notes": account.get("notes", ""),
        "has_password": bool(stored),
    }
    if reveal:
        payload["password"] = crypto.decrypt(stored) or ""
    return payload


def config_payload(
    row: ProjectConfig | None, key: str, *, name: str = "", reveal: bool = False
) -> dict[str, Any]:
    """Serialise a config row. ``reveal`` is the ONLY path to a plaintext password.

    The router sets it exclusively when the caller owns the row. A ``None`` row
    serialises to the empty config so an unconfigured project reads as blank
    rather than 404-ing the agent mid-run.

    ``updated_at`` is carried so a consumer mirroring this config can tell a stale
    copy from a current one (#147). It is the row's own timestamp, not the
    project's: a project row does not change when its configuration does, so
    polling the project would miss exactly the edits that matter here.
    """
    if row is None:
        return {
            "key": key,
            "name": name or key,
            "work_item_connection_id": None,
            "repository_connection_id": None,
            "base_url": "",
            "repos": [],
            "environments": [],
            "test_accounts": [],
            "extra": {},
            "manual_auth": False,
            "shared": True,
            # Nothing has ever been written, so there is no revision to report.
            # None is the honest answer and it is stable, which is what a polling
            # consumer needs — the first save gives them a timestamp to move to.
            "updated_at": None,
        }
    return {
        "key": row.key,
        "name": row.name or row.key,
        "work_item_connection_id": row.work_item_connection_id,
        "repository_connection_id": row.repository_connection_id,
        "base_url": row.base_url,
        "repos": get_repos(row),
        "environments": list(row.environments or []),
        "test_accounts": [
            _account_payload(a, reveal=reveal) for a in (row.test_accounts or [])
        ],
        "extra": dict(row.extra or {}),
        "manual_auth": bool(row.manual_auth),
        "shared": row.owner_id is None,
        "updated_at": row.updated_at,
    }


def config_etag(row: ProjectConfig | None, *, reveal: bool) -> str:
    """Validator for ``GET /projects/{key}/config`` (#147).

    Derived from the row's ``updated_at``, which ``onupdate=utcnow`` maintains on
    every write, so it changes exactly when the configuration does.

    **``reveal`` is part of the identity, not a detail.** The same row serialises
    differently depending on whether the caller owns it — test-account passwords
    are present for the owner and masked for everyone else. An ETag that ignored
    that would let a caller whose ownership changed revalidate against a cached
    body it is no longer entitled to, and be told `304`.

    A missing row still gets a stable validator rather than no header, so the
    "not configured yet" case revalidates like any other and does not silently
    fall back to full bodies forever.
    """
    stamp = "none" if row is None or row.updated_at is None else row.updated_at.isoformat()
    return f'W/"cfg-{stamp}-{"own" if reveal else "masked"}"'


# ----------------------------------------------------------- filesystem seams
#
# QAgent's version of this module also owned:
#
#   auth_path()/session_path()  -> workspace/<scope>/auth/<project>/storageState.json
#   auth_state()/clear_auth()   -> stat/unlink of that file
#
# None of it is ported. A saved Playwright session is a browser artifact
# produced on the machine that ran the browser, and the hub runs no browser and
# owns no workspace. ``manual_auth`` above records the *intent*; the agent owns
# the capture, the file and its lifecycle. If the hub ever needs to show "a
# session exists", the agent should report it as a value on ``extra`` (QAgent
# already does exactly that for its Local Agent, via ``extra.agentAuthCapturedAt``)
# rather than the hub gaining a filesystem.
