"""Per-owner workspace filesystem scope (ADR 0007).

The hub owned no workspace filesystem until knowledge builds moved here. Now it
does, and the same ``owner_id``-or-shared rule the database uses
(:mod:`app.services.ownership`) has to hold on disk too — otherwise two members'
same-keyed projects collide in one directory and a member's clone becomes
readable as the shared one.

    owner present            -> ``<workspace>/users/<owner_id>/<kind>/``
    owner absent (``None``)  -> ``<workspace>/shared/<kind>/``

Ported from QAgent's ``services/workspace_scope.py`` and cut to the three kinds
a build actually needs:

``repos``
    Shallow clones of application repositories.
``knowledge``
    The ``knowledge.md`` / ``knowledge.json`` artefacts a build emits.
``claude-config``
    The materialised Claude credential a build runs under. **Locked down** by
    :func:`app.services.claude_credentials.materialize`; see ADR 0007 —
    ``emehub-workspace`` holds plaintext credential material for the duration
    of a build and is not a volume to copy casually.

QAgent's ``specs`` / ``evidence`` / ``auth`` kinds are deliberately absent: the
hub runs no browser and generates no tests (ADR 0001, narrowed by ADR 0007).
"""

from __future__ import annotations

import re
from pathlib import Path

from app.config import settings

__all__ = [
    "CLAUDE_CONFIG",
    "KINDS",
    "KNOWLEDGE",
    "REPOS",
    "scope_for",
    "scoped_claude_config_dir",
    "scoped_dir",
    "scoped_knowledge_dir",
    "scoped_repos_dir",
    "slug",
]

REPOS = "repos"
KNOWLEDGE = "knowledge"
CLAUDE_CONFIG = "claude-config"

#: The only artefact kinds the hub keeps on disk.
KINDS = (REPOS, KNOWLEDGE, CLAUDE_CONFIG)


def scope_for(owner_id: int | None) -> str:
    """``"users/<id>"`` for an owned artefact, ``"shared"`` for the shared one."""
    return f"users/{owner_id}" if owner_id is not None else "shared"


def scoped_dir(kind: str, owner_id: int | None) -> Path:
    """The directory for ``kind`` in ``owner_id``'s scope. Not created here.

    Raises:
        ValueError: ``kind`` is not one of :data:`KINDS`. Deliberately strict —
            a typo would silently create a stray tree in the workspace volume.
    """
    if kind not in KINDS:
        raise ValueError(f"Unknown workspace kind '{kind}'")
    return settings.workspace_path / scope_for(owner_id) / kind


def scoped_repos_dir(owner_id: int | None) -> Path:
    return scoped_dir(REPOS, owner_id)


def scoped_knowledge_dir(owner_id: int | None) -> Path:
    return scoped_dir(KNOWLEDGE, owner_id)


def scoped_claude_config_dir(owner_id: int | None) -> Path:
    return scoped_dir(CLAUDE_CONFIG, owner_id)


def slug(value: str) -> str:
    """A filesystem-safe segment for a project/repo name.

    Every run of characters outside ``[a-zA-Z0-9._-]`` collapses to one ``-``,
    which also removes ``/`` and ``..`` — a project key is user-supplied, so this
    is the boundary that keeps it from escaping its scope directory.
    """
    cleaned = re.sub(r"[^a-zA-Z0-9._-]+", "-", value).strip("-.")
    return cleaned or "project"
