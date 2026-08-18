"""Provider operations that exist for DAgent, and only for DAgent.

DAgent (``ticket-executor``) drives a coding agent against a work item and then
against the pull request that work item produced. In "Part of EmeHub" mode it
holds no provider credential at all, so every one of those reads has to happen
here, on the side that has the PAT.

## Why this is a separate module

Two of the three things below have no other consumer in the hub, and the third
needs a fidelity the hub's own ticket store does not keep:

* **Pull requests.** Review threads, commits, per-commit diffs and merge
  outcomes. Nothing else in the hub has ever needed them — the existing ADO
  adapter resolves a linked PR *URL* and stops.
* **Per-type work item states.** ``list_work_item_metadata`` answers with the
  *union* of states across every work item type, which is the right answer for a
  filter dropdown and the wrong one for "what may this Bug transition to".
* **Full-fidelity tickets.** The hub's ``tickets`` table stores a description
  flattened to plain text and keeps no deep link, no original estimate and no
  story points. DAgent renders the rich text and prices runs against the
  estimate, so reading through the store would silently lose both.

Putting these in the existing adapters would change behaviour other callers
depend on. So this module is **additive and self-contained**: it reads a
connection, decrypts through the one function allowed to
(``connection_service.adapter_for``'s sibling path), and calls the provider
itself. No existing service or adapter is modified, and nothing outside
``routers/dagent.py`` imports this.

## Fidelity, and where it came from

The Azure DevOps logic here is a deliberate port of DAgent's own ``lib/ado.ts``,
not a fresh implementation. That file has absorbed several field-tested fixes
this code would otherwise have to rediscover, and each is preserved with the
reason it exists:

* A PR ref is resolved from the work item's ArtifactLink **and** from the PR URL
  the run recorded, each candidate verified against the repositories API before
  use. The artifact link's repository id goes stale (repo renamed or recreated,
  or it belongs to a repo this PAT cannot see) and then 404s every review call
  for that ticket.
* The repository GUID is resolved **org-wide**, with no project segment, because
  a work item's repo can live in a different project than the connection names.
* The PR's web URL is built from ``repository.webUrl`` when ADO returns it. A
  hand-built URL with an empty repo segment resolves to the project's PR *list*,
  which is a link that looks right and goes somewhere else.
* Only threads carrying a ``threadContext`` are review comments. The rest are
  ADO's own vote and status system threads, and counting them inflates every
  review metric.

## Failures

Everything raises ``ProviderError`` (or ``ProviderUnavailable`` for a routing
gap) rather than returning an empty list. An empty list that means "the call
failed" is precisely the ambiguity INTEGRATION.md §5 exists to forbid, and the
router maps these onto the status codes that keep them distinguishable.
"""

from __future__ import annotations

import base64
import difflib
import re
from concurrent.futures import ThreadPoolExecutor
from typing import Any
from urllib.parse import quote, urlsplit

import httpx

from app import crypto
from app.models.provider_connection import ProviderConnection
from app.services.adapters.azure_devops import API_VERSION, parse_org_url
from app.services.adapters.base import ProviderError

#: Work-item fields DAgent renders or prices a run against. Requested by name
#: rather than taking ADO's default projection: the default omits the two
#: estimate fields, and a missing estimate silently reads on DAgent's dashboard
#: as "the team sized this at nothing".
_TICKET_FIELDS = (
    "System.Id",
    "System.Title",
    "System.WorkItemType",
    "System.State",
    "System.AssignedTo",
    "System.AreaPath",
    "System.IterationPath",
    "System.Description",
    "Microsoft.VSTS.Common.AcceptanceCriteria",
    "Microsoft.VSTS.Scheduling.OriginalEstimate",
    "Microsoft.VSTS.Scheduling.StoryPoints",
    # The kanban column the item sits in, which is **not** its state: a board
    # maps several states onto one column and may carry custom columns, so
    # grouping a board view by state draws a different board than ADO does.
    "System.BoardColumn",
)

#: States that mean the item has left the board. Named literally because WIQL
#: cannot query ADO's state *category*, and the names differ per process
#: template — Agile closes at "Closed", Scrum and Basic at "Done", and both
#: Scrum and Agile use "Removed" for abandoned work. Only the backlog and board
#: scopes apply it; a sprint is bounded by its iteration and shows its closed
#: work on purpose.
_CLOSED_STATES = ("Closed", "Removed", "Done")

#: ADO's own cap on the ``ids`` parameter of the batch work-item read.
_BATCH_SIZE = 200

#: Cap on one sprint fetch, mirroring the adapter's. A 2000-item project must
#: not hang a page load.
MAX_TICKETS = 200

#: Guard against a pathological commit touching hundreds of files. Diffing each
#: one costs two content reads.
MAX_COMMIT_FILES = 60

#: ADO thread statuses that mean the reviewer considers the thread done.
_RESOLVED_THREAD_STATUSES = {"fixed", "closed", "wontfix"}

#: How many PRs to resolve at once. Two calls each, all against one org with one
#: PAT, so this is politeness to the provider rather than a throughput knob.
_OUTCOME_CHUNK = 6


class ProviderUnavailable(ProviderError):
    """The connection cannot serve this call — wrong kind, or nothing linked.

    A distinct type because it is a **routing** gap, not a provider failure: the
    router answers 404 for it and 502 for a plain ``ProviderError``, and
    conflating them tells the caller to retry something that will never work.
    """


# --------------------------------------------------------------- credentials
def _ado_context(connection: ProviderConnection) -> tuple[str, str, str]:
    """``(org_url, project, pat)`` for an Azure DevOps connection.

    Decrypts here for the same reason ``connection_service.adapter_for`` does,
    and with the same rule: a ciphertext that does not authenticate under the
    current key raises rather than being passed on as an empty credential. An
    empty PAT reads as "not configured" and would hide a key-rotation accident
    behind a plausible-looking error.
    """
    if connection.kind != "azure_devops":
        raise ProviderUnavailable(
            f"Connection {connection.id} is a '{connection.kind}' connection; "
            "DAgent pull-request and work-item reads are implemented for Azure "
            "DevOps only."
        )
    pat = crypto.decrypt(connection.pat_encrypted)
    if connection.pat_encrypted and pat is None:
        raise ProviderError(
            f"The stored credential for '{connection.display_name}' cannot be "
            "decrypted with the current encryption key"
        )
    config = connection.config or {}
    org_url, url_project = parse_org_url(
        config.get("orgUrl") or config.get("baseUrl") or connection.base_url or ""
    )
    if not org_url:
        raise ProviderError("Azure DevOps organisation URL is not configured")
    if not pat:
        raise ProviderError("Azure DevOps PAT is not configured")
    return org_url, (config.get("project") or "").strip() or url_project, pat


def _client(org_url: str, pat: str) -> httpx.Client:
    token = base64.b64encode(f":{pat}".encode()).decode()
    return httpx.Client(
        base_url=org_url,
        headers={"Authorization": f"Basic {token}", "Content-Type": "application/json"},
        timeout=30.0,
    )


def _scrubbed(exc: Exception, pat: str) -> ProviderError:
    """An httpx failure as a ``ProviderError`` with the PAT removed.

    An exception from httpx carries the request, and a request carries its
    headers. A log line is the easiest place in the system for a credential to
    end up somewhere nobody thinks to look for one.
    """
    message = str(exc).replace(pat, "***") if pat else str(exc)
    return ProviderError(message[:400])


def _get(client: httpx.Client, path: str, pat: str, **params: Any) -> dict[str, Any]:
    params.setdefault("api-version", API_VERSION)
    try:
        resp = client.get(path, params=params)
        resp.raise_for_status()
        return resp.json()
    except httpx.HTTPError as exc:
        raise _scrubbed(exc, pat) from exc


# ------------------------------------------------------------------- tickets
def _text(html: str) -> str:
    return html or ""


def _num(value: Any) -> float | None:
    """A numeric field, or None. **Never 0 as a stand-in for absent** — a zero
    estimate is a real answer that means something different from no estimate,
    and DAgent's value tier reads the two differently."""
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _ticket_url(org_url: str, project: str, work_item_id: Any) -> str:
    if not (org_url and project and work_item_id):
        return ""
    return f"{org_url.rstrip('/')}/{quote(project)}/_workitems/edit/{work_item_id}"


def _quoted(value: str) -> str:
    """A WIQL string literal's body. Doubling a quote is ADO's own escape — a
    sprint or project name with an apostrophe would otherwise terminate the
    literal and produce a syntax error."""
    return value.replace("'", "''")


def _wiql(project: str, sprint: str | None, scope: str) -> str:
    """The work items one view asks for.

    Three scopes, three different questions, and they are **not** filters over
    one list — each is bounded differently at the provider, which is why the
    scope has to reach this far rather than being applied to a sprint fetch
    after the fact:

    * ``sprint`` — the iteration named, or the team's current one.
      ``@currentIteration`` needs a team context ADO resolves from the project,
      so the no-sprint case is expressed with it rather than by naming a path,
      which is what lets a caller omit the sprint entirely and still get "now".
      Closed items are **kept**: a sprint is a record of what was worked on.
      ``sprint`` must already be a **rooted iteration path** — see
      :func:`_resolve_iteration_path`, which is where a bare name becomes one.
    * ``backlog`` — open work that is not scheduled into any iteration yet. In
      ADO that is the iteration path still sitting at the project root, since an
      unassigned work item inherits it.
    * ``board`` — every open work item in the project, regardless of iteration.
      That is what a kanban board shows, and it is the reason this is not the
      sprint query with a filter: a board's cards routinely live in iterations
      the sprint view would exclude.
    """
    clauses = [f"[System.TeamProject] = '{_quoted(project)}'"]
    if scope == "backlog":
        clauses.append(f"[System.IterationPath] = '{_quoted(project)}'")
    elif scope != "board":
        if sprint:
            clauses.append(f"[System.IterationPath] UNDER '{_quoted(sprint)}'")
        else:
            clauses.append("[System.IterationPath] = @currentIteration")
    if scope in ("backlog", "board"):
        closed = ",".join(f"'{s}'" for s in _CLOSED_STATES)
        clauses.append(f"[System.State] NOT IN ({closed})")
    where = " AND ".join(clauses)
    return f"SELECT [System.Id] FROM WorkItems WHERE {where} ORDER BY [System.Id] DESC"


def _resolve_iteration_path(
    connection: ProviderConnection, project: str, sprint: str
) -> str:
    """A caller's sprint as an iteration path WIQL will accept.

    ``System.IterationPath`` is a **rooted** path — ``RIS\\Sprint 61``, or
    ``RIS\\Release 1\\Sprint 61`` when the project nests its iterations. A bare
    leaf name is not one, and ADO does not treat that as "matches nothing": it
    rejects the whole query with a 400, which is what a caller sees when it
    passes the name a picker displayed.

    Costs an extra call **only** when the caller sent a bare name. A caller that
    passes back the ``path`` from ``/sprints`` — which is what it is there for —
    takes the first branch and pays nothing.

    A name that matches no iteration falls through to ``project\\name`` rather
    than raising. It is the right answer for the common flat layout, and a path
    that genuinely does not exist should come back as an empty sprint, which is
    a thing a user can act on, rather than as a 502 about a query they never saw.
    """
    if "\\" in sprint or "/" in sprint:
        return sprint.replace("/", "\\")
    leaf = sprint.strip()
    if not leaf or leaf == project:
        return project
    for row in list_sprints(connection, project=project):
        if row.get("name", "").strip().lower() == leaf.lower():
            return row.get("path") or f"{project}\\{leaf}"
    return f"{project}\\{leaf}"


def list_tickets(
    connection: ProviderConnection,
    *,
    project: str | None = None,
    sprint: str | None = None,
    scope: str = "sprint",
) -> tuple[list[dict[str, Any]], str, bool]:
    """A view's work items, in DAgent's own ticket shape.

    Read **live from the provider**, not from the hub's ``tickets`` table. That
    is the point of this function: the store flattens the description to plain
    text and keeps no deep link, estimate or story points, and DAgent needs all
    four. ``scope`` picks the view — see :func:`_wiql`.

    Returns ``(tickets, sprint_label, truncated)``. ``truncated`` is the honest
    half of ``MAX_TICKETS``: a backlog or board is not bounded by an iteration,
    so a big project silently losing its tail would read as a short board rather
    than a capped one.
    """
    org_url, default_project, pat = _ado_context(connection)
    proj = (project or "").strip() or default_project
    if not proj:
        raise ProviderUnavailable("No Azure DevOps project was given and the connection names none.")

    # Only the sprint scope reads it, and only as a rooted path.
    iteration = (
        _resolve_iteration_path(connection, proj, sprint) if sprint and scope == "sprint" else None
    )

    with _client(org_url, pat) as client:
        try:
            resp = client.post(
                f"/{quote(proj)}/_apis/wit/wiql",
                params={"api-version": API_VERSION},
                json={"query": _wiql(proj, iteration, scope)},
            )
            resp.raise_for_status()
            found = [str(w["id"]) for w in resp.json().get("workItems", [])]
        except httpx.HTTPError as exc:
            raise _scrubbed(exc, pat) from exc
        ids = found[:MAX_TICKETS]
        truncated = len(found) > len(ids)
        if not ids:
            return [], _scope_label(scope, sprint), False

        rows: list[dict[str, Any]] = []
        for i in range(0, len(ids), _BATCH_SIZE):
            chunk = ids[i : i + _BATCH_SIZE]
            data = _get(
                client,
                "/_apis/wit/workitems",
                pat,
                ids=",".join(chunk),
                fields=",".join(_TICKET_FIELDS),
            )
            rows.extend(data.get("value", []))

    tickets = [_normalize_ticket(row, org_url, proj) for row in rows]
    return tickets, _scope_label(scope, sprint, rows), truncated


def _scope_label(scope: str, sprint: str | None, rows: list[dict[str, Any]] | None = None) -> str:
    """What the caller's header should say this list is.

    Only the sprint scope has one to resolve: the caller may have omitted the
    sprint and let ``@currentIteration`` decide, and an empty label would then
    leave the picker blank. A backlog and a board span iterations, so naming one
    would be a claim that is not true.

    Always the **leaf**, whether the caller named a sprint or a whole path. A
    header chip is a name, and ``RIS\\Release 1\\Sprint 61`` is a location.
    """
    if scope != "sprint":
        return ""
    if sprint:
        return _leaf(sprint)
    if not rows:
        return ""
    return _leaf(rows[0].get("fields", {}).get("System.IterationPath", ""))


def _leaf(path: str) -> str:
    return (path or "").split("\\")[-1]


def _normalize_ticket(row: dict[str, Any], org_url: str, project: str) -> dict[str, Any]:
    f = row.get("fields", {}) or {}
    assigned = f.get("System.AssignedTo") or {}
    return {
        "id": str(row.get("id", "")),
        "title": f.get("System.Title", ""),
        "type": f.get("System.WorkItemType", ""),
        "status": f.get("System.State", ""),
        "assignee": assigned.get("displayName", "") if isinstance(assigned, dict) else "",
        # ADO's `uniqueName` is the sign-in address. DAgent matches it against the
        # configured personal account, which is how "only my tickets" works
        # without the two having to agree on display-name formatting.
        "assigneeEmail": assigned.get("uniqueName", "") if isinstance(assigned, dict) else "",
        "project": _leaf(f.get("System.AreaPath", "")) or project,
        "areaPath": f.get("System.AreaPath", ""),
        # Passed through as the provider's own HTML. DAgent sanitises it on
        # arrival; flattening it here is what the ticket store does, and it is
        # what loses the nested criteria and inline images real tickets use.
        "description": _text(f.get("System.Description", "")),
        "criteria": _text(f.get("Microsoft.VSTS.Common.AcceptanceCriteria", "")),
        "url": _ticket_url(org_url, project, row.get("id")),
        "estimateHours": _num(f.get("Microsoft.VSTS.Scheduling.OriginalEstimate")),
        "storyPoints": _num(f.get("Microsoft.VSTS.Scheduling.StoryPoints")),
        # Empty for a work item type that is not on a board (a Task, usually).
        # The caller falls back to the state, which is the closest true answer.
        "boardColumn": f.get("System.BoardColumn", "") or "",
    }


def list_sprints(connection: ProviderConnection, *, project: str | None = None) -> list[dict[str, Any]]:
    """The iterations a **team** is working, which is the list ADO itself shows.

    Project-scoped **by argument**, not by connection. DAgent picks a project in
    its own header and one connection spans a whole organisation, so resolving
    this from ``connection.config`` — which is what the shared adapter's
    ``list_sprints`` does — answers for whichever project the connection happens
    to name, and answers nothing at all when it names none. Either way the
    caller's sprint picker goes empty while its ticket list, which does take the
    project, keeps working: a picker that silently disagrees with the list
    beside it.

    **Team settings, not the classification tree.** The tree is every iteration
    the project has ever defined, across every team's sub-tree, and a project of
    any age answers with a soup — ``CPCAG Sprint 75`` next to
    ``FM-Schwab-Egnyte\\Sprint 8`` next to ``Sprint 47`` — that matches nothing a
    user sees in ADO, where a sprint list is always read under one team
    (``_sprints/backlog/<team>/…``). It also made "current" unanswerable: several
    of those sub-trees have a sprint spanning today, so dates matched more than
    one, and the picker highlighted a sprint the ticket list was not showing.

    No team segment, so ADO resolves the project's **default team** — the same
    context ``@currentIteration`` resolves through, which is what keeps the
    picker's default and a no-sprint ticket load agreeing. It is also what
    DAgent's own direct client does, so hub mode and direct mode show one list.

    ADO returns ``attributes.timeFrame`` here, so past/current/future is the
    provider's own classification rather than a guess made from two dates.
    """
    org_url, default_project, pat = _ado_context(connection)
    proj = (project or "").strip() or default_project
    if not proj:
        raise ProviderUnavailable("No Azure DevOps project was given and the connection names none.")

    with _client(org_url, pat) as client:
        data = _get(client, f"/{quote(proj)}/_apis/work/teamsettings/iterations", pat)

    sprints: list[dict[str, Any]] = []
    for row in data.get("value") or []:
        attrs = row.get("attributes") or {}
        sprints.append(
            {
                "id": str(row.get("id", "")),
                "name": row.get("name", ""),
                # Already the rooted `System.IterationPath` WIQL wants — this
                # endpoint returns `Project\Release 1\Sprint 2`, with no
                # structural `Iteration` segment to strip.
                "path": row.get("path", "") or row.get("name", ""),
                "start_date": attrs.get("startDate"),
                "finish_date": attrs.get("finishDate"),
                "time_frame": attrs.get("timeFrame") or "",
            }
        )
    return sprints


def ticket_status(connection: ProviderConnection, external_id: str) -> str:
    """One work item's current state, in one call.

    Deliberately a direct read rather than a filter over ``list_tickets``: DAgent
    calls this after every status write to display the provider's answer instead
    of an optimistic guess, and paying for a whole sprint fetch each time would
    make the honest path the slow one. It also works for a work item that has
    since left the current iteration, which the sprint query would not find.
    """
    org_url, _project, pat = _ado_context(connection)
    with _client(org_url, pat) as client:
        data = _get(client, f"/_apis/wit/workitems/{quote(external_id)}", pat, fields="System.State")
    return (data.get("fields") or {}).get("System.State", "")


def work_item_states(connection: ProviderConnection, work_item_type: str, *, project: str | None = None) -> list[str]:
    """The states **this** work item type may hold.

    Distinct from ``list_work_item_metadata``'s ``states``, which is the union
    across every type in the project. A status dropdown built from the union
    offers transitions the provider will reject — ADO process templates differ
    (Agile: New/Active/Resolved/Closed; Scrum: New/Approved/Committed/Done), and
    a literal PATCH of a state the type does not have is a 400.
    """
    org_url, default_project, pat = _ado_context(connection)
    proj = (project or "").strip() or default_project
    if not (proj and work_item_type):
        return []
    with _client(org_url, pat) as client:
        data = _get(
            client,
            f"/{quote(proj)}/_apis/wit/workitemtypes/{quote(work_item_type)}/states",
            pat,
            **{"api-version": "7.1-preview.1"},
        )
    return [s["name"] for s in data.get("value", []) if s.get("name")]


# ------------------------------------------------------------- pull requests
def _repo_base(ref: dict[str, Any]) -> str:
    """``.../repositories/{id}`` for a ref, org-wide when the project is unknown.

    The project segment is omitted deliberately when the ref does not carry one:
    ADO resolves a repository GUID across the whole organisation, and a work
    item's repository frequently lives in a different project than the one the
    connection names.
    """
    project_segment = f"{quote(ref['project'])}/" if ref.get("project") else ""
    return f"/{project_segment}_apis/git/repositories/{quote(str(ref['repositoryId']))}"


_ARTIFACT_RE = re.compile(r"vstfs:///Git/PullRequestId/[^%]+%2F([^%]+)%2F(\d+)", re.IGNORECASE)
_PR_URL_WITH_PROJECT = re.compile(r"/([^/]+)/_git/([^/]+)/pullrequest/(\d+)", re.IGNORECASE)
_PR_URL_BARE = re.compile(r"_git/([^/]+)/pullrequest/(\d+)", re.IGNORECASE)


def _refs_from_pr_url(url: str, default_project: str) -> list[dict[str, Any]]:
    from urllib.parse import unquote

    match = _PR_URL_WITH_PROJECT.search(url)
    if match:
        return [{
            "repositoryId": unquote(match.group(2)),
            "prId": match.group(3),
            "project": unquote(match.group(1)),
        }]
    match = _PR_URL_BARE.search(url)
    if match:
        return [{"repositoryId": unquote(match.group(1)), "prId": match.group(2), "project": default_project}]
    return []


def _resolve_ref(
    client: httpx.Client, pat: str, ticket_id: str | None, pr_url: str | None, default_project: str
) -> dict[str, Any] | None:
    """The PR this work item produced, from the artifact link or the recorded URL.

    Both sources are collected and then **verified against the repositories API**
    before one is used. ADO only creates the ArtifactLink relation when the PR was
    explicitly linked (an ``AB#<id>`` in its description), so a PR the agent opened
    may have none — and when it does have one, the repository id in it can be
    stale. Verifying is what turns "the link is wrong" into "fall through to the
    URL the run recorded" instead of a 404 on every review call for the ticket.
    """
    candidates: list[dict[str, Any]] = []
    if ticket_id:
        try:
            item = _get(client, f"/_apis/wit/workitems/{quote(ticket_id)}", pat, **{"$expand": "relations"})
            for relation in item.get("relations") or []:
                if relation.get("rel") != "ArtifactLink":
                    continue
                match = _ARTIFACT_RE.search(relation.get("url") or "")
                if match:
                    candidates.append({"repositoryId": match.group(1), "prId": match.group(2)})
        except ProviderError:
            # A work item we cannot read is not a reason to give up on a PR URL
            # the run already recorded.
            pass
    if pr_url:
        candidates.extend(_refs_from_pr_url(pr_url, default_project))

    for ref in candidates:
        try:
            repo = _get(client, _repo_base(ref), pat)
        except ProviderError:
            continue
        resolved = (repo.get("project") or {}).get("name") or ref.get("project")
        if resolved:
            return {**ref, "project": resolved}
    return None


def _pr_status(raw: dict[str, Any]) -> str:
    status = (raw.get("status") or "").lower()
    if status == "completed":
        return "Completed"
    if status == "abandoned":
        return "Abandoned"
    reviewers = raw.get("reviewers") or []
    if any((r.get("vote") or 0) <= -5 for r in reviewers):
        return "Changes requested"
    if reviewers and all((r.get("vote") or 0) >= 5 for r in reviewers):
        return "Approved"
    return "Active"


def _pr_web_url(org_url: str, project: str, raw: dict[str, Any], fallback: str | None) -> str:
    """The PR's page in the web UI.

    ``repository.webUrl`` is preferred because it is the one value guaranteed to
    name the repository the PR actually lives in. The hand-built form is a
    fallback and is never built from a partial ref: an empty repo segment yields
    ``.../_git//pullrequest/<n>``, which ADO serves as the project's pull-request
    *list* — a link that looks correct and goes somewhere else.
    """
    pr_id = raw.get("pullRequestId")
    repo = raw.get("repository") or {}
    web = repo.get("webUrl")
    if web:
        return f"{web.rstrip('/')}/pullrequest/{pr_id}"
    name = repo.get("name")
    if name and project:
        return f"{org_url.rstrip('/')}/{quote(project)}/_git/{quote(name)}/pullrequest/{pr_id}"
    return fallback or ""


def _is_review_thread(thread: dict[str, Any]) -> bool:
    """Anchored to a file, and carrying at least one real comment.

    ADO emits a thread for every vote and status change too. Counting those as
    review comments inflates the unresolved count on every screen that shows one.
    """
    if not thread.get("threadContext"):
        return False
    return any(
        not c.get("isDeleted") and c.get("commentType") != "system"
        for c in thread.get("comments") or []
    )


def _pr_overview(raw: dict[str, Any], org_url: str, project: str, fallback_url: str | None) -> dict[str, Any]:
    """One PR's identity, from either a single read or a row of a PR list — the
    two shapes are the same, which is what lets the batch path below skip the
    per-PR read entirely."""
    return {
        "id": str(raw.get("pullRequestId", "")),
        "url": _pr_web_url(org_url, project, raw, fallback_url),
        "title": raw.get("title", ""),
        "status": _pr_status(raw),
        "branch": (raw.get("sourceRefName") or "").removeprefix("refs/heads/"),
        "targetBranch": (raw.get("targetRefName") or "").removeprefix("refs/heads/"),
        "author": (raw.get("createdBy") or {}).get("displayName") or "Unknown",
        "reviewers": [r.get("displayName", "") for r in raw.get("reviewers") or [] if r.get("displayName")],
        "createdAt": raw.get("creationDate", ""),
    }


def _review_comments(threads: dict[str, Any]) -> list[dict[str, Any]]:
    """The review comments in a threads response, oldest first as ADO returns
    them. System and vote threads are dropped by ``_is_review_thread``."""
    comments: list[dict[str, Any]] = []
    for thread in threads.get("value") or []:
        if not _is_review_thread(thread):
            continue
        first = next(
            c for c in thread["comments"] if not c.get("isDeleted") and c.get("commentType") != "system"
        )
        context = thread.get("threadContext") or {}
        comments.append({
            "id": str(first.get("id") or thread.get("id")),
            "threadId": thread.get("id"),
            "author": (first.get("author") or {}).get("displayName") or "Unknown",
            "text": first.get("content") or "",
            "filePath": context.get("filePath") or "",
            "line": ((context.get("rightFileStart") or {}).get("line")),
            "status": "resolved" if (thread.get("status") or "").lower() in _RESOLVED_THREAD_STATUSES else "open",
            "date": first.get("publishedDate") or "",
        })
    return comments


def pull_request_review(
    connection: ProviderConnection, *, ticket_id: str | None, pr_url: str | None
) -> dict[str, Any]:
    """The linked PR and its review threads. ``{"pr": None, ...}`` when nothing
    is linked — which is a real answer, not a failure, and the only empty result
    in this module that does not raise."""
    org_url, default_project, pat = _ado_context(connection)
    with _client(org_url, pat) as client:
        ref = _resolve_ref(client, pat, ticket_id, pr_url, default_project)
        if not ref:
            return {"pr": None, "comments": [], "unresolvedCount": 0}

        base = _repo_base(ref)
        raw = _get(client, f"{base}/pullrequests/{ref['prId']}", pat)
        threads = _get(client, f"{base}/pullrequests/{ref['prId']}/threads", pat)

    pr = _pr_overview(raw, org_url, ref.get("project") or default_project, pr_url)
    comments = _review_comments(threads)
    return {
        "pr": pr,
        "comments": comments,
        "unresolvedCount": sum(1 for c in comments if c["status"] == "open"),
    }


def _resolve_for_summary(
    client: httpx.Client, pat: str, ticket_id: str, pr_url: str | None, default_project: str
) -> tuple[dict[str, Any], dict[str, Any]] | None:
    """``(ref, pull request)`` for a bell entry, in as few provider calls as it
    can be had.

    ``_resolve_ref`` is thorough and costs it: a work item read with relations
    expanded, then a repository read per candidate to verify it, *then* the PR
    itself — four calls for a ticket the caller usually already knows the PR URL
    of. That is the right trade for the detail tab, where it happens once for one
    open ticket. It is the wrong one for a bell polling a board on a timer.

    So when a PR URL was recorded, its ref is tried **directly**: the PR read is
    itself the verification, since a repository or PR that does not resolve
    answers 404 and nothing is built from the guess. Two calls in the common
    case. A URL that no longer resolves falls back to the artifact link rather
    than being reported as "no PR" — that fallback is the whole reason the
    thorough path exists (a renamed or recreated repository), and skipping it
    would turn an optimisation into a silently emptier bell.

    It also does **not** reuse ``_resolve_ref``, for one reason: that function
    swallows a failed work item read, on the grounds that a PR URL may still
    resolve. Here the work item is the last source, so swallowing it turns a
    revoked PAT into "this ticket has no PR" for every ticket on the board —
    an outage rendered as an empty bell. Errors from it propagate, and the
    caller records the item as unresolved instead.

    Returns ``None`` only when the provider answered and nothing is linked.
    """
    if pr_url:
        for ref in _refs_from_pr_url(pr_url, default_project):
            try:
                return ref, _get(client, f"{_repo_base(ref)}/pullrequests/{ref['prId']}", pat)
            except ProviderError:
                break  # stale URL — fall through to the artifact link

    if not ticket_id:
        return None

    item = _get(client, f"/_apis/wit/workitems/{quote(ticket_id)}", pat, **{"$expand": "relations"})
    for relation in item.get("relations") or []:
        if relation.get("rel") != "ArtifactLink":
            continue
        match = _ARTIFACT_RE.search(relation.get("url") or "")
        if not match:
            continue
        ref: dict[str, Any] = {"repositoryId": match.group(1), "prId": match.group(2)}
        try:
            # The repository read resolves the project, which the artifact link
            # does not carry and the PR's web URL is built from.
            repo = _get(client, _repo_base(ref), pat)
            ref["project"] = (repo.get("project") or {}).get("name") or default_project
            return ref, _get(client, f"{_repo_base(ref)}/pullrequests/{ref['prId']}", pat)
        except ProviderError:
            continue  # stale link — try the next relation
    return None


def _summarize(ticket_id: str, pr: dict[str, Any], comments: list[dict[str, Any]]) -> dict[str, Any]:
    """One entry: which PR this ticket resolved to, and how much is open on it.

    Only the count and the newest open comment travel, never the thread bodies —
    a board's worth of full review payloads is most of what this endpoint exists
    to stop sending.

    An entry is returned even when **nothing** is open, and that is the point of
    the shape. ``unresolvedCount: 0`` is not a notification, but it does tell the
    caller which PR this ticket is on, and a PR with nothing open is the common
    case. Answering ``None`` there would leave exactly those tickets re-resolving
    from the work item on every poll, for the rest of their lives.
    """
    unresolved = [c for c in comments if c["status"] == "open"]
    latest = unresolved[-1] if unresolved else None
    return {
        "ticketId": ticket_id,
        "prId": pr["id"],
        "prUrl": pr["url"],
        "prTitle": pr["title"],
        "author": pr["author"],
        "reviewers": pr["reviewers"],
        "unresolvedCount": len(unresolved),
        "latestAuthor": latest["author"] if latest else "",
        "latestText": latest["text"] if latest else "",
        "latestDate": latest["date"] if latest else "",
    }


def review_summaries(
    connection: ProviderConnection, items: list[dict[str, Any]]
) -> list[dict[str, Any] | None]:
    """Unresolved-review-comment summaries for many work items, in one request.

    DAgent's review bell used to ask ``/pull-request`` once per ticket on every
    poll, which is one HTTP round-trip per ticket across the network *and* the
    full comment payload for each, almost all of it discarded on arrival. This
    answers the whole board at once and carries only what the bell renders.

    Answers **positionally**, with ``None`` both for "no PR linked" and for "this
    one item could not be resolved" — the bell draws nothing either way, and one
    deleted PR must not blank out the rest of the board.

    Whole-batch failure is different and does raise. Every item failing is the
    signature of a revoked PAT or an unreachable provider, and answering 200 with
    a list of nulls would render as "you have no reviews" — the exact ambiguity
    INTEGRATION.md §5 forbids.
    """
    if not items:
        return []
    org_url, default_project, pat = _ado_context(connection)
    failures: list[str] = []

    def one(item: dict[str, Any]) -> dict[str, Any] | None:
        ticket_id = str(item.get("ticketId") or "")
        pr_url = item.get("prUrl") or None
        try:
            with _client(org_url, pat) as client:
                resolved = _resolve_for_summary(client, pat, ticket_id, pr_url, default_project)
                if not resolved:
                    return None
                ref, raw = resolved
                threads = _get(client, f"{_repo_base(ref)}/pullrequests/{ref['prId']}/threads", pat)
        except ProviderError as exc:
            failures.append(str(exc))
            return None
        pr = _pr_overview(raw, org_url, ref.get("project") or default_project, pr_url)
        return _summarize(ticket_id, pr, _review_comments(threads))

    with ThreadPoolExecutor(max_workers=_OUTCOME_CHUNK) as pool:
        out = list(pool.map(one, items))

    if len(failures) == len(items):
        raise ProviderError(failures[0])
    return out


def pull_request_commits(
    connection: ProviderConnection, *, ticket_id: str | None, pr_url: str | None
) -> list[dict[str, Any]]:
    """Every commit on the PR's source branch, newest first as ADO returns them."""
    org_url, default_project, pat = _ado_context(connection)
    with _client(org_url, pat) as client:
        ref = _resolve_ref(client, pat, ticket_id, pr_url, default_project)
        if not ref:
            return []
        data = _get(client, f"{_repo_base(ref)}/pullrequests/{ref['prId']}/commits", pat)

    project = ref.get("project") or default_project
    out = []
    for commit in data.get("value") or []:
        sha = commit.get("commitId", "")
        author = commit.get("author") or {}
        out.append({
            "sha": sha,
            "shortSha": sha[:7],
            "message": (commit.get("comment") or "").splitlines()[0] if commit.get("comment") else "",
            "author": author.get("name") or "Unknown",
            "date": author.get("date") or "",
            "url": f"{org_url.rstrip('/')}/{quote(project)}/_git/{quote(str(ref['repositoryId']))}/commit/{sha}",
        })
    return out


_CHANGE_TYPES = {"add": "added", "delete": "deleted"}


def _change_type(raw: str) -> str:
    if raw in _CHANGE_TYPES:
        return _CHANGE_TYPES[raw]
    return "renamed" if "rename" in (raw or "").lower() else "modified"


def _item_text(client: httpx.Client, pat: str, ref: dict[str, Any], path: str, sha: str) -> str | None:
    """File content at a commit, or None when the path did not exist there.

    404 is a normal answer (the file was added, or deleted) and is distinguished
    from a failure, which raises — otherwise a transient error renders as an
    empty side of the diff and the file looks wholly added or wholly removed.
    """
    try:
        resp = client.get(
            f"{_repo_base(ref)}/items",
            params={
                "path": path,
                "versionDescriptor.version": sha,
                "versionDescriptor.versionType": "commit",
                "api-version": API_VERSION,
                "$format": "text",
            },
        )
    except httpx.HTTPError as exc:
        raise _scrubbed(exc, pat) from exc
    if resp.status_code == 404:
        return None
    if resp.status_code >= 400:
        raise ProviderError(f"Azure DevOps returned {resp.status_code} reading {path}")
    return resp.text


def _unified_diff(path: str, before: str | None, after: str | None) -> dict[str, Any]:
    old = (before or "").splitlines(keepends=True)
    new = (after or "").splitlines(keepends=True)
    lines = list(difflib.unified_diff(old, new, fromfile=f"a/{path}", tofile=f"b/{path}"))
    additions = sum(1 for line in lines if line.startswith("+") and not line.startswith("+++"))
    deletions = sum(1 for line in lines if line.startswith("-") and not line.startswith("---"))
    return {"diff": "".join(lines), "additions": additions, "deletions": deletions}


def commit_files(
    connection: ProviderConnection, sha: str, *, ticket_id: str | None, pr_url: str | None
) -> list[dict[str, Any]]:
    """Per-file changes for one commit, each with a unified diff.

    ADO has no "give me the patch" endpoint, so the diff is built here from the
    file's content at this commit and at its first parent — two reads per file,
    which is why the file count is capped.
    """
    org_url, default_project, pat = _ado_context(connection)
    with _client(org_url, pat) as client:
        ref = _resolve_ref(client, pat, ticket_id, pr_url, default_project)
        if not ref:
            return []
        base = _repo_base(ref)
        changes = _get(client, f"{base}/commits/{quote(sha)}/changes", pat)
        detail = _get(client, f"{base}/commits/{quote(sha)}", pat)
        parent = (detail.get("parents") or [None])[0]

        files = [
            c for c in changes.get("changes") or []
            if (c.get("item") or {}).get("path") and not (c.get("item") or {}).get("isFolder")
        ][:MAX_COMMIT_FILES]

        out = []
        for change in files:
            path = change["item"]["path"]
            kind = _change_type(change.get("changeType") or "edit")
            before = None if kind == "added" or not parent else _safe_item(client, pat, ref, path, parent)
            after = None if kind == "deleted" else _safe_item(client, pat, ref, path, sha)
            out.append({"path": path, "changeType": kind, **_unified_diff(path, before, after)})
    return out


def _safe_item(client: httpx.Client, pat: str, ref: dict[str, Any], path: str, sha: str) -> str | None:
    """One side of a diff, tolerating a read that fails.

    Unlike ``_item_text`` this swallows the error: one unreadable side of one
    file should render as a one-sided diff, not fail the whole commit view.
    """
    try:
        return _item_text(client, pat, ref, path, sha)
    except ProviderError:
        return None


def pull_request_outcomes(connection: ProviderConnection, pr_urls: list[str]) -> list[dict[str, Any] | None]:
    """What became of each PR: merged, abandoned, and how many review threads.

    Answers positionally, with ``None`` for a URL that no longer resolves — one
    stale PR must not blank out the whole delivery funnel. Two calls per PR, so
    the caller caps the list.
    """
    org_url, default_project, pat = _ado_context(connection)

    def resolve(url: str) -> dict[str, Any] | None:
        refs = _refs_from_pr_url(url, default_project)
        if not refs:
            return None
        ref = refs[0]
        try:
            with _client(org_url, pat) as client:
                base = _repo_base(ref)
                raw = _get(client, f"{base}/pullrequests/{ref['prId']}", pat)
                threads = _get(client, f"{base}/pullrequests/{ref['prId']}/threads", pat)
        except ProviderError:
            return None
        status = (raw.get("status") or "").lower()
        return {
            "merged": status == "completed",
            "abandoned": status == "abandoned",
            "reviewComments": sum(1 for t in threads.get("value") or [] if _is_review_thread(t)),
        }

    out: list[dict[str, Any] | None] = []
    with ThreadPoolExecutor(max_workers=_OUTCOME_CHUNK) as pool:
        out.extend(pool.map(resolve, pr_urls))
    return out
