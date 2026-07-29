"""Clone a repository into the owner's workspace, for a hub-side build (ADR 0007).

Ported from QAgent's ``services/repo_service.py`` with one behavioural change
and one hardening change.

## The behavioural change: no ``local_repo_path``

QAgent resolves a configured ``local_repo_path`` first and clones only as a
fallback. The hub must not: ``local_repo_path`` is an **agent-host** path
(``project_config_service.REPO_FIELDS``) that the hub stores, echoes and never
resolves. A directory of that name inside the API container is either absent or,
worse, something else entirely. So the hub clones, always, from ``repo_url``.

## The hardening change: the authenticated URL never escapes

Cloning a private repository means putting the repository connection's PAT into
an HTTPS URL (ADR 0007; the connection is resolved through
``connection_service.resolve_repository_for_project``). git treats that URL as
ordinary text and reproduces it in its own error output —
``fatal: could not read from remote repository https://<pat>@github.com/…`` is a
real message. Three rules follow, and all three are enforced here rather than
trusted to callers:

1. the authenticated URL is built as late as possible and passed only to
   ``subprocess``; it is never logged, never returned, never stored;
2. every log line about a clone uses :func:`redact`, which strips any
   ``scheme://userinfo@`` span regardless of what the userinfo was;
3. every git stream that becomes a message goes through *both*
   :func:`redact` and ``adapters.base.scrub`` with the PAT as an explicit
   secret — belt and braces, because git can also print the token bare (in a
   ``.git-credentials`` warning, say) where there is no ``@`` to match on.

:func:`ensure_clone` therefore raises :class:`CloneError` whose ``str()`` is
already safe to write into ``ProjectKnowledge.last_error``.

## The second hardening change: git may never ask a human

The PAT is a *password*, so it goes in the password half of the userinfo
(:func:`_authenticated_url`). A PAT in the *username* half with nothing after
the colon is not "authenticated" to git — it is a username whose password is
still missing, so git goes looking for one. In a container with no TTY that is
``fatal: could not read Password for 'https://***@dev.azure.com': No such
device or address``, and with an inherited askpass helper it is a hang until
``clone_timeout_s``. :func:`_git_env` closes both doors, so a wrong credential
fails immediately with a message that says which.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path
from urllib.parse import quote, urlparse, urlunparse

from sqlalchemy.orm import Session

from app.config import settings
from app.logging import logger
from app.services import connection_service
from app.services.adapters.base import ProviderError, scrub
from app.services.workspace_scope import scoped_repos_dir, slug

__all__ = ["CloneError", "ProviderError", "ensure_clone", "redact"]

#: Any ``scheme://userinfo@host`` span, whatever the userinfo holds.
_USERINFO = re.compile(r"([a-zA-Z][a-zA-Z0-9+.-]*://)[^@\s/]+@")

#: How much git output reaches a message. Enough to identify the failure,
#: bounded so a verbose git cannot fill the ``last_error`` column.
_DETAIL_LIMIT = 400

#: The username half of ``https://<user>:<pat>@host``. A PAT is a *password*, so
#: something has to sit in the username position. Azure DevOps ignores it
#: entirely; GitHub accepts any username when the password is a PAT. This is the
#: name GitHub's own Actions checkout uses, so it is also the least surprising
#: thing to see in a log line that somehow escaped redaction.
_PAT_USERNAME = "x-access-token"

#: Environment variables that can turn a credential failure into a *prompt* —
#: either an interactive one (no TTY in the container, hence
#: ``No such device or address``) or a GUI helper that hangs until
#: ``clone_timeout_s``. Dropped from the inherited environment and then pinned
#: to their inert values by :func:`_git_env`.
_INTERACTIVE_VARS = (
    "GIT_ASKPASS",
    "SSH_ASKPASS",
    "GCM_INTERACTIVE",
    "GIT_TERMINAL_PROMPT",
    "DISPLAY",
    "SSH_ASKPASS_REQUIRE",
)


class CloneError(RuntimeError):
    """A clone or refresh failed. ``str()`` is scrubbed and safe to store."""


def redact(text: str, *secrets: str | None) -> str:
    """Strip embedded credentials from anything about to be logged or stored.

    Both mechanisms, always: the structural one (a ``//user:pass@host`` span)
    and the literal one (the PAT we know we injected). Either alone has a real
    gap — the structural rule misses a bare token, the literal rule misses a
    *different* credential git found in its own config.
    """
    return _USERINFO.sub(r"\1***@", scrub(text, *secrets))


def _authenticated_url(url: str, pat: str) -> str:
    """Inject ``pat`` into an HTTPS URL that carries no credentials of its own.

    The PAT goes in the **password** position — ``https://<user>:<pat>@host``.
    Putting it in the *username* position with no password (which this function
    used to do) is what made every private clone fail: git reads a bare username
    as "the password is still missing", asks for it, finds no TTY in the
    container, and dies with ``could not read Password for
    'https://***@dev.azure.com': No such device or address``.

    Both halves are percent-encoded. A PAT is opaque provider output and may
    legally contain ``/``, ``@``, ``:`` or ``#``, every one of which would
    otherwise re-parse the URL into a different host or path.

    Non-HTTPS URLs and URLs that already have userinfo are returned untouched —
    the hub never rewrites a credential someone else put there.
    """
    if not pat or not url.startswith("https://"):
        return url
    parsed = urlparse(url)
    if "@" in parsed.netloc:
        return url
    userinfo = f"{quote(_PAT_USERNAME, safe='')}:{quote(pat, safe='')}"
    return urlunparse(parsed._replace(netloc=f"{userinfo}@{parsed.netloc}"))


def _secrets(pat: str) -> tuple[str, str]:
    """The PAT in both the forms that can appear in git's output.

    :func:`_authenticated_url` percent-encodes what it injects, so a PAT with a
    URL-unsafe character reaches git — and comes back in its error text — in a
    form the raw literal would not match.
    """
    return (pat, quote(pat, safe="") if pat else "")


def _git_env() -> dict[str, str]:
    """The environment every git subprocess runs under.

    Built explicitly rather than inherited: git resolves missing credentials
    through whatever helper the ambient environment names, so an inherited
    ``GIT_ASKPASS`` or ``SSH_ASKPASS`` turns "this PAT is wrong" into a hang
    until ``clone_timeout_s``, and no helper at all turns it into the
    ``No such device or address`` prompt failure. ``GIT_TERMINAL_PROMPT=0``
    closes the last door, so a bad credential fails in milliseconds with a
    message that says so.

    The rest of the process environment is carried through — git needs ``PATH``,
    ``HOME`` and the TLS trust store to work at all.
    """
    env = {k: v for k, v in os.environ.items() if k not in _INTERACTIVE_VARS}
    env["GIT_TERMINAL_PROMPT"] = "0"
    # Empty, not absent: git falls straight through an empty askpass program.
    env["GIT_ASKPASS"] = ""
    env["SSH_ASKPASS"] = ""
    env["GCM_INTERACTIVE"] = "never"
    return env


def _run_git(args: list[str], *, pat: str) -> tuple[bool, str]:
    """Run git and return ``(ok, scrubbed_detail)``. Never raises, never logs raw.

    ``args`` may contain the authenticated URL; nothing derived from it reaches
    the return value or the log without passing through :func:`redact`.
    """
    try:
        proc = subprocess.run(  # fixed argv, no shell
            ["git", *args],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=settings.clone_timeout_s,
            check=False,
            env=_git_env(),
        )
    except FileNotFoundError:
        return False, "git is not installed in the API image"
    except subprocess.TimeoutExpired:
        return False, f"git timed out after {settings.clone_timeout_s}s"
    except OSError as exc:
        return False, redact(str(exc), *_secrets(pat))[:_DETAIL_LIMIT]
    if proc.returncode != 0:
        detail = redact(
            (proc.stderr or proc.stdout or "").strip(), *_secrets(pat)
        )[:_DETAIL_LIMIT]
        return False, detail or f"git exited {proc.returncode}"
    return True, ""


def _rmtree(path: Path) -> None:
    shutil.rmtree(path, ignore_errors=True)


def _pat_for(db: Session, *, owner_id: int | None, bound_connection_id: int | None) -> str:
    """The clone credential, resolved through the project's repository binding.

    Not best-effort, unlike QAgent's: a hub build that silently degrades to an
    anonymous clone produces a confusing "repository not found" from git for
    what is really "you have not connected GitHub". The caller turns the
    :class:`ProviderError` into an ``error`` status with that sentence on it.
    """
    connection = connection_service.resolve_repository_for_project(
        db, viewer_id=owner_id, bound_connection_id=bound_connection_id
    )
    return connection_service.repository_pat(connection)


def ensure_clone(
    db: Session,
    *,
    project_key: str,
    repo_name: str,
    repo_url: str,
    owner_id: int | None,
    bound_connection_id: int | None,
) -> Path:
    """Clone or refresh ``repo_url`` under ``owner_id``'s workspace; return the path.

    The destination is ``<workspace>/<scope>/repos/<project>[/<repo>]`` — scoped
    by owner so two members' same-named projects never share a checkout, and
    slugged so a project key cannot escape its scope directory.

    An existing checkout is refreshed (``fetch --depth 1`` + ``reset --hard``)
    and re-cloned from scratch if that cannot reconcile; a fresh one is a
    ``git clone --depth 1``. Shallow throughout: a build reads the working tree,
    never the history.

    Raises:
        CloneError: no URL, or git failed. The message is scrubbed.
        ProviderError: no repository connection, or its PAT will not decrypt.
    """
    url = (repo_url or "").strip()
    if not url:
        raise CloneError(
            "This repository has no clone URL. Add one under Project settings › "
            "Repositories, then build again."
        )

    pat = _pat_for(db, owner_id=owner_id, bound_connection_id=bound_connection_id)
    authed = _authenticated_url(url, pat)

    dest = scoped_repos_dir(owner_id) / slug(project_key)
    if repo_name:
        dest = dest / slug(repo_name)

    if (dest / ".git").is_dir():
        logger.info("Refreshing %s in %s", redact(url, *_secrets(pat)), dest)
        ok, _detail = _run_git(["-C", str(dest), "fetch", "--depth", "1", "origin"], pat=pat)
        if ok:
            ok, _detail = _run_git(["-C", str(dest), "reset", "--hard", "FETCH_HEAD"], pat=pat)
        if ok:
            return dest
        logger.info("Refresh failed for %s — re-cloning", redact(url, *_secrets(pat)))
        _rmtree(dest)

    dest.parent.mkdir(parents=True, exist_ok=True)
    logger.info("Cloning %s into %s", redact(url, *_secrets(pat)), dest)
    ok, detail = _run_git(["clone", "--depth", "1", authed, str(dest)], pat=pat)
    if not ok:
        _rmtree(dest)
        raise CloneError(f"Could not clone {redact(url, *_secrets(pat))}: {detail}")
    return dest
