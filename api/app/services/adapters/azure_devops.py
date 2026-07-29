"""Azure DevOps adapter — work items (WIQL) and Git repositories.

Talks to the real Azure DevOps REST API over ``httpx``. Authenticates with HTTP
basic auth, empty username and the PAT as the password (the ADO convention).

Config: ``orgUrl`` / ``baseUrl`` (e.g. ``https://dev.azure.com/emesoft``),
``project`` (default project name). Secret: ``pat``.

Two behaviours come from DAgent's ``lib/ado.ts`` rather than QAgent, because
QAgent's adapter is missing them and both are real bugs in the field:

* :func:`parse_org_url` — users paste the *project* URL, not the org URL, and
  the legacy ``{org}.visualstudio.com`` host is still live. Both now parse.
* :meth:`AzureDevOpsAdapter.update_status` resolves the requested state against
  the work item type's **actual** configured states before writing. ADO process
  templates differ (Agile: New/Active/Resolved/Closed; Scrum:
  New/Approved/Committed/Done; Basic: To Do/Doing/Done), so a literal PATCH of
  "Done" is rejected outright on an Agile project.
"""

from __future__ import annotations

import base64
import json
import re
from typing import Any
from urllib.parse import quote, unquote, urlsplit

import httpx

from app.logging import logger
from app.services.adapters import register
from app.services.adapters.base import (
    NormalizedTicket,
    ProviderAdapter,
    ProviderError,
    scrub,
)

API_VERSION = "7.1"
COMMENTS_API_VERSION = "7.1-preview.3"

# QA-relevant work item types across the common process templates (Agile, Scrum,
# Basic). A value that does not exist simply never matches inside a WIQL IN()
# list — it is not a 400 — so listing a superset is safe.
_WORK_ITEM_TYPES = (
    "User Story",
    "Product Backlog Item",
    "Bug",
    "Task",
    "Feature",
    "Issue",
)

#: Cap on a single fetch. A 2000-item project must not hang a sync.
MAX_SYNC_ITEMS = 200

#: ADO's own cap on the ``ids`` parameter of the batch work-item read.
_BATCH_SIZE = 200


class _WiqlError(RuntimeError):
    """A 400 from the WIQL endpoint, carrying ADO's own validation message."""


# ---------------------------------------------------------------- parsing
def parse_org_url(raw: str | None) -> tuple[str, str]:
    """Split whatever the user pasted into ``(org_url, project)``.

    Accepts the full project URL (the normal case — it is what the ADO web UI
    puts in the address bar), an org-only URL, the legacy
    ``{org}.visualstudio.com`` host, and bare ``dev.azure.com/org/project`` text
    with no scheme. Path segments are URL-decoded, so ``Application%20Support``
    comes back as ``Application Support``.

    Returns ``("", "")`` for empty input rather than raising — an unconfigured
    connection is a normal state, and the error belongs at the call that needs
    the value.
    """
    trimmed = (raw or "").strip().rstrip("/")
    if not trimmed:
        return "", ""
    with_scheme = trimmed if re.match(r"^https?://", trimmed, re.IGNORECASE) else f"https://{trimmed}"
    parts = urlsplit(with_scheme)
    host = (parts.hostname or "").lower()
    if not host:
        return "", ""
    scheme = parts.scheme or "https"
    port = f":{parts.port}" if parts.port else ""
    segments = [_decode(s) for s in parts.path.split("/") if s]

    # Legacy host: https://{org}.visualstudio.com/{project}
    if host.endswith(".visualstudio.com"):
        return f"{scheme}://{host}{port}", (segments[0] if segments else "")

    # https://dev.azure.com/{org}[/{project}] — and on-prem TFS collections,
    # where the first segment is the collection and plays the org's role.
    org = segments[0] if segments else ""
    project = segments[1] if len(segments) > 1 else ""
    org_url = f"{scheme}://{host}{port}"
    if org:
        org_url = f"{org_url}/{quote(org)}"
    return org_url, project


def _decode(segment: str) -> str:
    try:
        return unquote(segment).strip()
    except (TypeError, ValueError):  # pragma: no cover - unquote is total
        return segment.strip()


def _wiql_literal(value: str) -> str:
    """Escape a value for a single-quoted WIQL string literal."""
    return value.replace("'", "''")


def _xml_escape(value: str) -> str:
    return (
        (value or "")
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _steps_xml(steps: list[dict[str, Any]]) -> str:
    """Serialise steps into the Azure DevOps TCM Steps XML format."""
    if not steps:
        return '<steps id="0" last="1"></steps>'
    parts = []
    for i, step in enumerate(steps, start=2):
        action = _xml_escape(step.get("a", ""))
        expected = _xml_escape(step.get("e", ""))
        parts.append(
            f'<step id="{i}" type="ActionStep">'
            f'<parameterizedString isformatted="true">{action}</parameterizedString>'
            f'<parameterizedString isformatted="true">{expected}</parameterizedString>'
            f"<description/></step>"
        )
    return f'<steps id="0" last="{len(steps) + 1}">{"".join(parts)}</steps>'


def _json_bytes(value: Any) -> bytes:
    """Serialise a JSON-patch body to bytes, so the json-patch content type sticks."""
    return json.dumps(value).encode("utf-8")


def _classification_path_to_iteration(node_path: str) -> str:
    """Convert a classification-node path to a ``System.IterationPath`` value.

    ``\\Surency\\Iteration\\Release 1\\Sprint 3`` becomes
    ``Surency\\Release 1\\Sprint 3`` — strip the leading separator and the
    structural ``Iteration`` / ``Area`` segment, which WIQL does not use.
    """
    parts = [p for p in node_path.split("\\") if p]
    if len(parts) >= 2 and parts[1] in ("Iteration", "Area"):
        parts = [parts[0]] + parts[2:]
    return "\\".join(parts)


def _strip_html(html: str) -> str:
    """Best-effort HTML → plain text for ADO's rich-text fields."""
    if not html:
        return ""
    text = re.sub(r"<br\s*/?>", "\n", html, flags=re.IGNORECASE)
    # A list item opens on its own line. Without the leading newline every
    # <li> in a <ul> runs into the previous one and acceptance criteria come
    # back as a single blob — QAgent's adapter has exactly that bug.
    text = re.sub(r"<li[^>]*>", "\n- ", text, flags=re.IGNORECASE)
    text = re.sub(r"</(p|li|ul|ol|div|h[1-6]|tr)\s*>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", "", text)
    return (
        text.replace("&nbsp;", " ")
        .replace("&amp;", "&")
        .replace("&lt;", "<")
        .replace("&gt;", ">")
        .strip()
    )


def _split_ac(text: str) -> list[str]:
    """Split acceptance-criteria text into one entry per criterion."""
    if not text:
        return []
    return [line for line in (ln.strip("-• \t") for ln in text.splitlines()) if line]


class AzureDevOpsAdapter(ProviderAdapter):
    kind = "azure_devops"

    def __init__(self, config: dict, secrets: dict, *, transport=None) -> None:
        super().__init__(config, secrets, transport=transport)
        raw_url = self.config.get("orgUrl") or self.config.get("baseUrl") or ""
        self.org_url, url_project = parse_org_url(raw_url)
        # An explicit project wins; otherwise take the one in the pasted URL.
        self.project = (self.config.get("project") or "").strip() or url_project
        self.pat = self.secrets.get("pat") or ""

    def _client(self) -> httpx.Client:
        if not self.org_url:
            raise ProviderError("Azure DevOps organisation URL is not configured")
        if not self.pat:
            raise ProviderError("Azure DevOps PAT is not configured")
        token = base64.b64encode(f":{self.pat}".encode()).decode()
        return self._http(
            base_url=self.org_url,
            headers={
                "Authorization": f"Basic {token}",
                "Content-Type": "application/json",
            },
        )

    def _require_project(self) -> str:
        if not self.project:
            raise ProviderError("Azure DevOps project is not configured")
        return self.project

    def _scrub(self, value: Any) -> str:
        return scrub(value, self.pat)

    # -- Connectivity -----------------------------------------------------
    def test_connection(self) -> dict[str, Any]:
        try:
            with self._client() as client:
                resp = client.get(f"/_apis/projects?api-version={API_VERSION}")
                resp.raise_for_status()
                data = resp.json()
            count = data.get("count", len(data.get("value", [])))
            return {
                "ok": True,
                "message": f"Connected to Azure DevOps ({count} projects visible)",
                "detail": {"count": count},
            }
        except ProviderError as exc:
            return {"ok": False, "message": str(exc), "detail": {}}
        except httpx.HTTPStatusError as exc:
            return {
                "ok": False,
                "message": f"Azure DevOps returned {exc.response.status_code}",
                "detail": {"statusCode": exc.response.status_code},
            }
        except httpx.HTTPError as exc:
            return {
                "ok": False,
                "message": f"Azure DevOps connection failed: {self._scrub(exc)}",
                "detail": {},
            }

    # -- Read -------------------------------------------------------------
    def list_projects(self) -> list[dict[str, Any]]:
        with self._client() as client:
            resp = client.get(f"/_apis/projects?api-version={API_VERSION}")
            resp.raise_for_status()
            data = resp.json()
        return [
            {
                "external_id": str(p.get("id", "")),
                "name": p.get("name", ""),
                "state": p.get("state", ""),
            }
            for p in data.get("value", [])
        ]

    def list_sprints(self) -> list[dict[str, Any]]:
        """Enumerate the project's iterations from its classification nodes.

        Uses the project-scoped iteration tree (no team context required) and
        converts each node's classification path into the ``System.IterationPath``
        form WIQL expects.
        """
        project = self._require_project()
        with self._client() as client:
            resp = client.get(
                f"/{quote(project)}/_apis/wit/classificationnodes/iterations",
                params={"$depth": 10, "api-version": API_VERSION},
            )
            resp.raise_for_status()
            root = resp.json()

        sprints: list[dict[str, Any]] = []

        def walk(node: dict[str, Any]) -> None:
            for child in node.get("children") or []:
                attrs = child.get("attributes") or {}
                sprints.append(
                    {
                        "id": str(child.get("identifier") or child.get("id", "")),
                        "name": child.get("name", ""),
                        "path": _classification_path_to_iteration(child.get("path", "")),
                        "start_date": attrs.get("startDate"),
                        "finish_date": attrs.get("finishDate"),
                    }
                )
                walk(child)

        walk(root)
        return sprints

    def list_repos(self) -> list[dict[str, Any]]:
        """The Git repositories in the configured ADO project."""
        project = self._require_project()
        with self._client() as client:
            resp = client.get(
                f"/{quote(project)}/_apis/git/repositories",
                params={"api-version": API_VERSION},
            )
            resp.raise_for_status()
            data = resp.json()
        return [
            {
                "name": r.get("name", ""),
                "clone_url": r.get("remoteUrl", ""),
                "web_url": r.get("webUrl") or r.get("remoteUrl", ""),
                "default_branch": (r.get("defaultBranch") or "").removeprefix("refs/heads/"),
            }
            for r in data.get("value", [])
        ]

    def list_work_item_metadata(self) -> dict[str, Any]:
        """Area paths, work item types and the union of their states."""
        empty = {"area_paths": [], "work_item_types": [], "states": [], "epics": []}
        if not self.project:
            return empty
        area_paths: list[dict[str, Any]] = []
        types: list[str] = []
        states: set[str] = set()
        with self._client() as client:
            areas = client.get(
                f"/{quote(self.project)}/_apis/wit/classificationnodes/areas",
                params={"$depth": 10, "api-version": API_VERSION},
            )
            if areas.status_code < 400:

                def walk(node: dict[str, Any]) -> None:
                    for child in node.get("children") or []:
                        area_paths.append(
                            {
                                "id": str(child.get("identifier") or child.get("id", "")),
                                "name": child.get("name", ""),
                                "path": _classification_path_to_iteration(child.get("path", "")),
                            }
                        )
                        walk(child)

                walk(areas.json())

            wits = client.get(
                f"/{quote(self.project)}/_apis/wit/workitemtypes",
                params={"api-version": API_VERSION},
            )
            if wits.status_code < 400:
                for wit in wits.json().get("value", []):
                    if wit.get("name"):
                        types.append(wit["name"])
                    for state in wit.get("states") or []:
                        if state.get("name"):
                            states.add(state["name"])
        return {
            "area_paths": area_paths,
            "work_item_types": types,
            "states": sorted(states),
            "epics": [],
        }

    def fetch_tickets(
        self,
        *,
        mode: str = "sprint",
        sprint: str | None = None,
        sprint_path: str | None = None,
        area_path: str | None = None,
        states: list[str] | None = None,
        work_item_types: list[str] | None = None,
        ticket_ids: list[str] | None = None,
        include_comments: bool = False,
        project: str | None = None,
    ) -> list[NormalizedTicket]:
        project = (project or "").strip() or self._require_project()
        with self._client() as client:
            ids = self._query_work_item_ids(
                client,
                project,
                mode=mode,
                sprint=sprint,
                sprint_path=sprint_path,
                area_path=area_path,
                states=states,
                work_item_types=work_item_types,
                ticket_ids=ticket_ids,
            )
            if not ids:
                return []
            if len(ids) > MAX_SYNC_ITEMS:
                logger.warning(
                    "Azure DevOps sync capped at %s of %s work items", MAX_SYNC_ITEMS, len(ids)
                )
                ids = ids[:MAX_SYNC_ITEMS]
            items = self._get_work_items(client, ids)
            return [
                self._normalize(client, item, include_comments=include_comments)
                for item in items
            ]

    def fetch_comments(self, ticket_external_id: str) -> list[dict[str, Any]]:
        if not str(ticket_external_id).isdigit():
            return []
        with self._client() as client:
            return self._fetch_comments(client, int(ticket_external_id))

    # -- Query ------------------------------------------------------------
    def _query_work_item_ids(
        self,
        client: httpx.Client,
        project: str,
        *,
        mode: str,
        sprint: str | None,
        sprint_path: str | None,
        area_path: str | None,
        states: list[str] | None,
        work_item_types: list[str] | None,
        ticket_ids: list[str] | None,
    ) -> list[int]:
        if mode == "selected" and ticket_ids:
            return [int(tid) for tid in ticket_ids if str(tid).isdigit()]

        type_list = work_item_types or list(_WORK_ITEM_TYPES)
        types = ", ".join(f"'{_wiql_literal(t)}'" for t in type_list)
        base_conditions = [
            f"[System.TeamProject] = '{_wiql_literal(project)}'",
            f"[System.WorkItemType] IN ({types})",
        ]
        if states:
            state_list = ", ".join(f"'{_wiql_literal(s)}'" for s in states)
            base_conditions.append(f"[System.State] IN ({state_list})")
        else:
            base_conditions.append("[System.State] <> 'Removed'")
        if area_path:
            base_conditions.append(f"[System.AreaPath] UNDER '{_wiql_literal(area_path)}'")

        conditions = list(base_conditions)
        iteration = sprint_path or (f"{project}\\{sprint}" if sprint else None)
        if mode == "sprint" and iteration:
            conditions.append(f"[System.IterationPath] UNDER '{_wiql_literal(iteration)}'")
        elif mode == "assigned":
            conditions.append("[System.AssignedTo] = @Me")

        try:
            return self._run_wiql(client, project, conditions)
        except _WiqlError as exc:
            # The commonest WIQL 400 is an iteration path that does not exist in
            # this project. Retry once without the iteration filter so the sync
            # still returns something; otherwise surface ADO's own message.
            if mode == "sprint" and iteration:
                logger.warning(
                    "Azure DevOps rejected the iteration filter (%s); retrying unscoped",
                    self._scrub(exc),
                )
                return self._run_wiql(client, project, base_conditions)
            raise ProviderError(
                f"Azure DevOps WIQL query failed: {self._scrub(exc)}"
            ) from exc

    def _run_wiql(self, client: httpx.Client, project: str, conditions: list[str]) -> list[int]:
        query = (
            "SELECT [System.Id] FROM WorkItems WHERE "
            + " AND ".join(conditions)
            + " ORDER BY [System.ChangedDate] DESC"
        )
        resp = client.post(
            f"/{quote(project)}/_apis/wit/wiql?api-version={API_VERSION}",
            json={"query": query},
        )
        if resp.status_code == 400:
            try:
                message = resp.json().get("message") or resp.text
            except ValueError:
                message = resp.text
            raise _WiqlError(str(message).strip())
        resp.raise_for_status()
        return [wi["id"] for wi in resp.json().get("workItems", [])]

    def _get_work_items(self, client: httpx.Client, ids: list[int]) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        for start in range(0, len(ids), _BATCH_SIZE):
            batch = ids[start : start + _BATCH_SIZE]
            resp = client.get(
                "/_apis/wit/workitems",
                params={
                    "ids": ",".join(str(i) for i in batch),
                    "$expand": "relations",
                    "api-version": API_VERSION,
                },
            )
            resp.raise_for_status()
            items.extend(resp.json().get("value", []))
        return items

    # -- Normalisation ----------------------------------------------------
    def _normalize(
        self, client: httpx.Client, item: dict[str, Any], *, include_comments: bool = False
    ) -> NormalizedTicket:
        fields = item.get("fields", {})
        wi_id = item.get("id")

        assigned_to = fields.get("System.AssignedTo") or {}
        assignee = (
            assigned_to.get("displayName", "")
            if isinstance(assigned_to, dict)
            else str(assigned_to)
        )
        ac_html = fields.get("Microsoft.VSTS.Common.AcceptanceCriteria", "") or ""
        attachments, linked_prs = self._parse_relations(item.get("relations") or [])
        team_project = fields.get("System.TeamProject") or self.project

        return NormalizedTicket(
            external_id=str(wi_id),
            provider_kind=self.kind,
            title=fields.get("System.Title", ""),
            work_item_type=fields.get("System.WorkItemType", "User Story"),
            status=fields.get("System.State", ""),
            priority=self._map_priority(fields.get("Microsoft.VSTS.Common.Priority")),
            assignee=assignee,
            sprint=(fields.get("System.IterationPath") or "").split("\\")[-1],
            area_path=fields.get("System.AreaPath") or "",
            epic="",
            description=_strip_html(fields.get("System.Description", "")),
            note="",
            url=self._web_url(team_project, wi_id),
            labels=[t.strip() for t in (fields.get("System.Tags") or "").split(";") if t.strip()],
            acceptance_criteria=_split_ac(_strip_html(ac_html)),
            acceptance_criteria_html=ac_html,
            comments=self._fetch_comments(client, wi_id) if include_comments else [],
            attachments=attachments,
            linked_prs=linked_prs,
        )

    def _web_url(self, project: str, wi_id: Any) -> str:
        if not (self.org_url and project and wi_id is not None):
            return ""
        return f"{self.org_url}/{quote(str(project))}/_workitems/edit/{wi_id}"

    @staticmethod
    def _map_priority(value: Any) -> str:
        try:
            n = int(value)
        except (TypeError, ValueError):
            return "Medium"
        if n <= 1:
            return "High"
        if n == 2:
            return "Medium"
        return "Low"

    def _fetch_comments(self, client: httpx.Client, wi_id: Any) -> list[dict[str, Any]]:
        try:
            resp = client.get(
                f"/_apis/wit/workItems/{wi_id}/comments",
                params={"api-version": COMMENTS_API_VERSION},
            )
            resp.raise_for_status()
        except httpx.HTTPError:
            # Comments are decoration on a ticket; a 403 from a PAT without the
            # scope must not fail the whole sync.
            return []
        return [
            {
                "who": (c.get("createdBy") or {}).get("displayName", ""),
                "when": c.get("createdDate", ""),
                "text": _strip_html(c.get("text", "")),
            }
            for c in resp.json().get("comments", [])
        ]

    def _parse_relations(
        self, relations: list[dict[str, Any]]
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        attachments: list[dict[str, Any]] = []
        linked_prs: list[dict[str, Any]] = []
        for rel in relations:
            rel_type = rel.get("rel", "")
            url = rel.get("url", "")
            attrs = rel.get("attributes", {}) or {}
            if rel_type == "AttachedFile":
                attachments.append(
                    {"name": attrs.get("name") or url.rsplit("/", 1)[-1], "size": ""}
                )
            elif "PullRequest" in rel_type or ("ArtifactLink" in rel_type and "PullRequest" in url):
                linked_prs.append(self._parse_pr_artifact(url))
        return attachments, linked_prs

    def _parse_pr_artifact(self, url: str) -> dict[str, Any]:
        """Turn an ADO pull-request artifact link into a clickable PR entry.

        The relation url is a vstfs artifact of the shape
        ``vstfs:///Git/PullRequestId/{projectId}%2F{repoId}%2F{prId}``. Take the
        segment after ``PullRequestId/``, URL-decode it and split on ``/`` to
        recover ``[projectId, repoId, prId]``; ``prId`` is the PR number, and the
        GUIDs resolve fine in an ADO web URL. Pure string work — no extra
        per-PR request during a bulk sync. Unexpected input falls back to the
        raw trailing segment rather than raising.
        """
        marker = "PullRequestId/"
        idx = url.find(marker)
        if idx != -1:
            parts = _decode(url[idx + len(marker) :]).split("/")
            if len(parts) == 3 and all(parts):
                project_id, repo_id, pr_id = parts
                return {
                    "repo": "",
                    "num": pr_id,
                    "title": f"PR !{pr_id}",
                    "status": "",
                    "url": f"{self.org_url}/{project_id}/_git/{repo_id}/pullrequest/{pr_id}",
                }
        return {"repo": "", "num": url.rsplit("/", 1)[-1], "title": "", "status": "", "url": ""}

    # -- Write ------------------------------------------------------------
    def publish_comment(
        self,
        ticket_external_id: str,
        body: str,
        *,
        attachments: list[str] | None = None,
    ) -> str:
        with self._client() as client:
            resp = client.post(
                f"/_apis/wit/workItems/{ticket_external_id}/comments",
                params={"api-version": COMMENTS_API_VERSION},
                json={"text": body},
            )
            resp.raise_for_status()
            return str(resp.json().get("id", ""))

    def update_status(self, ticket_external_id: str, target_status: str) -> None:
        """Transition the work item, mapping the request onto a real state.

        See the module docstring: process templates disagree on state names, so
        the literal label is resolved against the work item type's configured
        states first. An unresolvable label raises rather than sending a PATCH
        Azure DevOps will reject with an opaque 400.
        """
        with self._client() as client:
            state = self._resolve_state(client, ticket_external_id, target_status)
            if state is None:
                raise ProviderError(
                    f"No Azure DevOps state matching '{target_status}' on work item "
                    f"{ticket_external_id}"
                )
            resp = client.patch(
                f"/_apis/wit/workitems/{ticket_external_id}?api-version={API_VERSION}",
                headers={"Content-Type": "application/json-patch+json"},
                content=_json_bytes(
                    [{"op": "add", "path": "/fields/System.State", "value": state}]
                ),
            )
            resp.raise_for_status()

    def _resolve_state(
        self, client: httpx.Client, ticket_external_id: str, desired: str
    ) -> str | None:
        """Map ``desired`` onto one of the work item type's configured states.

        Exact case-insensitive match first, then any state sharing a word with
        the request ("Code Review" → "Resolved" will not match; "Done" → "Done"
        and "Closed" → "Closed" will). Returns ``None`` when nothing matches, so
        the caller can refuse rather than guess. If the metadata lookup itself
        fails, the literal label is returned — better to let ADO adjudicate than
        to block a transition on a metadata hiccup.
        """
        want = (desired or "").strip()
        if not want:
            return None
        try:
            resp = client.get(
                f"/_apis/wit/workitems/{ticket_external_id}",
                params={
                    "fields": "System.WorkItemType,System.TeamProject",
                    "api-version": API_VERSION,
                },
            )
            resp.raise_for_status()
            fields = resp.json().get("fields") or {}
            wit_type = fields.get("System.WorkItemType")
            project = fields.get("System.TeamProject") or self.project
            if not (wit_type and project):
                return want
            states_resp = client.get(
                f"/{quote(project)}/_apis/wit/workitemtypes/{quote(wit_type)}/states",
                params={"api-version": API_VERSION},
            )
            states_resp.raise_for_status()
            states = [s.get("name", "") for s in states_resp.json().get("value", []) if s.get("name")]
        except httpx.HTTPError:
            return want
        if not states:
            return want

        lowered = want.lower()
        for state in states:
            if state.lower() == lowered:
                return state
        words = [w for w in lowered.split() if w]
        for state in states:
            if any(word in state.lower() for word in words):
                return state
        return None

    def list_test_cases(self, ticket_external_id: str | None = None) -> list[dict[str, Any]]:
        """The project's ``Test Case`` work items as ``{external_id, title, state}``."""
        if not self.project:
            return []
        with self._client() as client:
            try:
                ids = self._run_wiql(
                    client,
                    self.project,
                    [
                        f"[System.TeamProject] = '{_wiql_literal(self.project)}'",
                        "[System.WorkItemType] = 'Test Case'",
                        "[System.State] <> 'Removed'",
                    ],
                )
            except _WiqlError:
                return []
            if not ids:
                return []
            items = self._get_work_items(client, ids[:MAX_SYNC_ITEMS])
        return [
            {
                "external_id": str(it.get("id", "")),
                "title": (it.get("fields") or {}).get("System.Title", ""),
                "state": (it.get("fields") or {}).get("System.State", ""),
            }
            for it in items
        ]

    def create_test_case(
        self,
        ticket_external_id: str,
        *,
        title: str,
        precondition: str = "",
        steps: list[dict[str, Any]] | None = None,
        priority: str = "Medium",
        link: bool = True,
    ) -> dict[str, Any]:
        """Create a ``Test Case`` work item with TCM steps, related to the ticket."""
        project = self._require_project()
        prio = {"High": 1, "Medium": 2, "Low": 3}.get(priority, 2)
        patch: list[dict[str, Any]] = [
            {"op": "add", "path": "/fields/System.Title", "value": title},
            {"op": "add", "path": "/fields/Microsoft.VSTS.Common.Priority", "value": prio},
            {
                "op": "add",
                "path": "/fields/Microsoft.VSTS.TCM.Steps",
                "value": _steps_xml(steps or []),
            },
        ]
        if precondition:
            patch.append(
                {
                    "op": "add",
                    "path": "/fields/System.Description",
                    "value": _xml_escape(precondition),
                }
            )
        with self._client() as client:
            resp = client.post(
                f"/{quote(project)}/_apis/wit/workitems/$Test%20Case",
                params={"api-version": API_VERSION},
                headers={"Content-Type": "application/json-patch+json"},
                content=_json_bytes(patch),
            )
            if resp.status_code >= 400:
                raise ProviderError(
                    f"Azure DevOps create test case failed ({resp.status_code}): "
                    f"{self._scrub(resp.text[:300])}"
                )
            created = resp.json()
            tc_id = created.get("id")
            web_url = ((created.get("_links") or {}).get("html") or {}).get("href", "")

            linked = False
            if link:
                rel = client.patch(
                    f"/_apis/wit/workitems/{tc_id}?api-version={API_VERSION}",
                    headers={"Content-Type": "application/json-patch+json"},
                    content=_json_bytes(
                        [
                            {
                                "op": "add",
                                "path": "/relations/-",
                                "value": {
                                    "rel": "System.LinkTypes.Related",
                                    "url": (
                                        f"{self.org_url}/_apis/wit/workItems/"
                                        f"{ticket_external_id}"
                                    ),
                                    "attributes": {"comment": "EmeHub generated test case"},
                                },
                            }
                        ]
                    ),
                )
                linked = rel.status_code < 400
        return {
            "external_id": str(tc_id),
            "url": web_url or self._web_url(project, tc_id),
            "status": "Design",
            "linked": linked,
        }


register(AzureDevOpsAdapter.kind, AzureDevOpsAdapter)
