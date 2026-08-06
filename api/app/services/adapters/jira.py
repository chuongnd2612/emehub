"""Jira adapter — issues as work items.

Talks to the real Jira Cloud REST API (v3) over ``httpx``, authenticating with
HTTP basic auth: the account email plus an API token.

Config: ``baseUrl`` (e.g. ``https://emesoft.atlassian.net``), ``project``
(default project key), ``email`` (the Atlassian account address).
Secret: ``pat`` (the API token).

The email lives in ``config``, not in the secret store — it is an identifier,
not a credential, and keeping exactly one secret per connection is what lets the
hub say ``hasPat`` and mean it. QAgent stored ``{email, apiToken}`` as two
encrypted secrets; ``apiToken`` is still accepted as an alias so a migrated row
keeps working.

Jira supplies work items only. It hosts no git repositories, so a Jira
connection can never carry the ``repository`` capability.
"""

from __future__ import annotations

from typing import Any

import httpx

from app.services.adapters import register
from app.services.adapters.base import (
    NormalizedTicket,
    ProviderAdapter,
    ProviderError,
    scrub,
)
from app.services.jql import build_jql, issue_keys_jql, quote

API_PREFIX = "/rest/api/3"
AGILE_PREFIX = "/rest/agile/1.0"

#: Best-effort custom field ids. Both vary per Jira instance; an instance that
#: numbers them differently degrades to "no acceptance criteria" / "no epic"
#: rather than failing the sync.
ACCEPTANCE_CRITERIA_FIELD = "customfield_10020"
EPIC_LINK_FIELD = "customfield_10014"

_MAX_RESULTS = 200


def _adf_to_text(node: Any) -> str:
    """Best-effort Atlassian Document Format → plain text."""
    if node is None:
        return ""
    if isinstance(node, str):
        return node
    if not isinstance(node, dict):
        return ""

    node_type = node.get("type")
    if node_type == "text":
        return node.get("text", "")

    parts = [_adf_to_text(child) for child in node.get("content", [])]
    if node_type in ("paragraph", "heading"):
        text = "".join(parts)
    else:
        text = "\n".join(p for p in parts if p)

    if node_type == "paragraph":
        return text + "\n"
    if node_type == "listItem":
        return "- " + text
    return text


def _text_to_adf(text: str) -> dict:
    """Wrap plain text into a minimal Atlassian Document Format document."""
    lines = text.split("\n") if text else [""]
    return {
        "type": "doc",
        "version": 1,
        "content": [
            {"type": "paragraph", "content": [{"type": "text", "text": line or " "}]}
            for line in lines
        ],
    }


def _split_ac(text: str) -> list[str]:
    if not text:
        return []
    return [line for line in (ln.strip("-• \t") for ln in text.splitlines()) if line]


class JiraAdapter(ProviderAdapter):
    kind = "jira"
    # Neither is implemented here: issue comments arrive with the issue in
    # ``fetch_tickets``, and Jira's test-case story lives in Xray/Zephyr —
    # separate products with their own APIs. Both flags stay False so an agent is
    # told "not supported" rather than "there are none". An explicit decision,
    # not an oversight.
    supports_comments = False
    supports_test_cases = False

    def __init__(self, config: dict, secrets: dict, *, transport=None) -> None:
        super().__init__(config, secrets, transport=transport)
        raw = self.config.get("baseUrl") or self.config.get("orgUrl") or ""
        self.base_url = raw.strip().rstrip("/")
        self.project = (self.config.get("project") or "").strip()
        self.email = (self.config.get("email") or "").strip()
        # `apiToken` is QAgent's key for the same value; accepted for migrated rows.
        self.api_token = self.secrets.get("pat") or self.secrets.get("apiToken") or ""

    def _client(self) -> httpx.Client:
        if not self.base_url:
            raise ProviderError("Jira site URL is not configured")
        if not self.email:
            raise ProviderError("Jira account email is not configured")
        if not self.api_token:
            raise ProviderError("Jira API token is not configured")
        return self._http(
            base_url=self.base_url,
            auth=(self.email, self.api_token),
            headers={"Accept": "application/json", "Content-Type": "application/json"},
        )

    def _scrub(self, value: Any) -> str:
        return scrub(value, self.api_token)

    # -- Connectivity -----------------------------------------------------
    def test_connection(self) -> dict[str, Any]:
        try:
            with self._client() as client:
                resp = client.get(f"{API_PREFIX}/myself")
                resp.raise_for_status()
                data = resp.json()
            return {
                "ok": True,
                "message": f"Connected to Jira as {data.get('displayName', self.email)}",
                "detail": {"accountId": data.get("accountId", "")},
            }
        except ProviderError as exc:
            return {"ok": False, "message": str(exc), "detail": {}}
        except httpx.HTTPStatusError as exc:
            return {
                "ok": False,
                "message": f"Jira returned {exc.response.status_code}",
                "detail": {"statusCode": exc.response.status_code},
            }
        except httpx.HTTPError as exc:
            return {
                "ok": False,
                "message": f"Jira connection failed: {self._scrub(exc)}",
                "detail": {},
            }

    # -- Read -------------------------------------------------------------
    def list_projects(self) -> list[dict[str, Any]]:
        with self._client() as client:
            resp = client.get(f"{API_PREFIX}/project/search")
            resp.raise_for_status()
            data = resp.json()
        return [
            {"external_id": p.get("key", ""), "name": p.get("name") or p.get("key", "")}
            for p in data.get("values", [])
        ]

    def list_sprints(self) -> list[dict[str, Any]]:
        """Active and future sprints across the project's agile boards.

        ``path`` is the numeric sprint id — ``sprint = <id>`` is the only JQL
        form that is unambiguous when two boards reuse a sprint name.
        Best-effort: a project with no agile board yields an empty list.
        """
        if not self.project:
            return []
        sprints: dict[str, dict[str, Any]] = {}
        try:
            with self._client() as client:
                boards = client.get(
                    f"{AGILE_PREFIX}/board", params={"projectKeyOrId": self.project}
                )
                boards.raise_for_status()
                for board in boards.json().get("values", []):
                    resp = client.get(
                        f"{AGILE_PREFIX}/board/{board['id']}/sprint",
                        params={"state": "active,future"},
                    )
                    if resp.status_code != 200:
                        continue
                    for sprint in resp.json().get("values", []):
                        sid = str(sprint.get("id"))
                        sprints[sid] = {
                            "id": sid,
                            "name": sprint.get("name", sid),
                            "path": sid,
                            "start_date": sprint.get("startDate"),
                            "finish_date": sprint.get("endDate"),
                            "state": sprint.get("state"),
                        }
        except httpx.HTTPError:
            pass
        return list(sprints.values())

    def list_work_item_metadata(self) -> dict[str, Any]:
        """Issue types, statuses and epics. Jira has no area paths."""
        types: list[str] = []
        states: list[str] = []
        epics: list[dict[str, str]] = []
        try:
            with self._client() as client:
                issue_types = client.get(f"{API_PREFIX}/issuetype")
                if issue_types.status_code < 400:
                    types = sorted({t.get("name", "") for t in issue_types.json() if t.get("name")})
                statuses = client.get(f"{API_PREFIX}/status")
                if statuses.status_code < 400:
                    states = sorted({s.get("name", "") for s in statuses.json() if s.get("name")})
                jql = (
                    f"project = {self.project} AND issuetype = Epic"
                    if self.project
                    else "issuetype = Epic"
                )
                found = client.post(
                    f"{API_PREFIX}/search/jql",
                    json={"jql": jql, "maxResults": 100, "fields": ["summary"]},
                )
                if found.status_code < 400:
                    epics = [
                        {
                            "key": issue.get("key", ""),
                            "name": (issue.get("fields") or {}).get("summary", ""),
                        }
                        for issue in found.json().get("issues", [])
                    ]
        except httpx.HTTPError:
            pass
        return {"area_paths": [], "work_item_types": types, "states": states, "epics": epics}

    def count_tickets(self, *, spec: Any = None, project: str | None = None) -> int:
        """The real total, from Jira's own count endpoint.

        Separate from :meth:`fetch_tickets` because that one is capped at
        ``_MAX_RESULTS`` so a bulk sync cannot hang, and a capped number is the wrong
        answer to "how many are there" — it reads as the truth. Jira's newer
        ``/search/jql`` deliberately returns no total (it pages by token), so the
        count comes from ``approximate-count``, which exists for exactly this. An
        instance too old to have it falls back to the base class, cap and all.
        """
        jql = self._compile(spec=spec, project=project)
        try:
            with self._client() as client:
                resp = client.post(f"{API_PREFIX}/search/approximate-count", json={"jql": jql})
                if resp.status_code < 400:
                    return int(resp.json().get("count", 0))
        except (httpx.HTTPError, ValueError, TypeError):
            pass
        return super().count_tickets(spec=spec, project=project)

    def fetch_tickets(
        self,
        *,
        mode: str = "sprint",
        sprint: str | None = None,
        sprint_path: str | None = None,
        area_path: str | None = None,  # ADO-only; unused
        states: list[str] | None = None,
        work_item_types: list[str] | None = None,
        ticket_ids: list[str] | None = None,
        include_comments: bool = False,  # Jira returns comments inline
        project: str | None = None,
        spec: Any = None,
    ) -> list[NormalizedTicket]:
        jql = self._compile(
            spec=spec,
            mode=mode,
            sprint=sprint,
            sprint_path=sprint_path,
            states=states,
            work_item_types=work_item_types,
            ticket_ids=ticket_ids,
            project=project,
        )
        with self._client() as client:
            resp = client.post(
                f"{API_PREFIX}/search/jql",
                json={
                    "jql": jql,
                    "maxResults": _MAX_RESULTS,
                    "fields": [
                        "summary",
                        "status",
                        "priority",
                        "assignee",
                        "sprint",
                        "description",
                        "labels",
                        "comment",
                        "attachment",
                        "issuetype",
                        "parent",
                        ACCEPTANCE_CRITERIA_FIELD,
                        EPIC_LINK_FIELD,
                    ],
                },
            )
            resp.raise_for_status()
            data = resp.json()
        return [self._normalize(issue) for issue in data.get("issues", [])]

    def _compile(
        self,
        *,
        spec: Any = None,
        mode: str = "all",
        sprint: str | None = None,
        sprint_path: str | None = None,
        states: list[str] | None = None,
        work_item_types: list[str] | None = None,
        ticket_ids: list[str] | None = None,
        project: str | None = None,
    ) -> str:
        """The JQL to run: the compiled clause query when there is one.

        A compiled query **replaces** the legacy selection outright rather than
        blending with it. Mixing the two would silently re-apply a condition the
        user had removed, which is the same rule the Azure DevOps adapter follows.
        """
        if spec is not None:
            return build_jql(spec, (project or "").strip() or self.project)
        return self._build_jql(
            mode=mode,
            sprint=sprint,
            sprint_path=sprint_path,
            states=states,
            work_item_types=work_item_types,
            ticket_ids=ticket_ids,
            project=project,
        )

    def _build_jql(
        self,
        *,
        mode: str,
        sprint: str | None,
        sprint_path: str | None = None,
        states: list[str] | None = None,
        work_item_types: list[str] | None = None,
        ticket_ids: list[str] | None = None,
        project: str | None = None,
    ) -> str:
        if mode == "selected" and ticket_ids:
            return issue_keys_jql(ticket_ids)

        conditions: list[str] = []
        proj = (project or "").strip() or self.project
        if proj:
            conditions.append(f"project = {quote(proj)}")
        if mode == "sprint" and (sprint_path or sprint):
            if sprint_path and str(sprint_path).isdigit():
                # A sprint id is an integer field; digits cannot carry an injection.
                conditions.append(f"sprint = {sprint_path}")
            else:
                conditions.append(f"sprint = {quote(str(sprint or sprint_path))}")
        elif mode == "assigned":
            conditions.append("assignee = currentUser()")
        if states:
            conditions.append("status IN (" + ", ".join(quote(s) for s in states) + ")")
        if work_item_types:
            conditions.append("issuetype IN (" + ", ".join(quote(t) for t in work_item_types) + ")")
        return " AND ".join(conditions) if conditions else "order by created DESC"

    # -- Normalisation ----------------------------------------------------
    def _normalize(self, issue: dict[str, Any]) -> NormalizedTicket:
        fields = issue.get("fields", {}) or {}
        key = issue.get("key", "")
        assignee = (fields.get("assignee") or {}).get("displayName", "")
        priority = (fields.get("priority") or {}).get("name", "Medium")
        status = (fields.get("status") or {}).get("name", "")
        issue_type = (fields.get("issuetype") or {}).get("name", "User Story")

        ac_field = fields.get(ACCEPTANCE_CRITERIA_FIELD)
        if isinstance(ac_field, dict):
            ac_text = _adf_to_text(ac_field)
        elif isinstance(ac_field, str):
            ac_text = ac_field
        else:
            ac_text = ""

        comments = [
            {
                "who": (c.get("author") or {}).get("displayName", ""),
                "when": c.get("created", ""),
                "text": _adf_to_text(c.get("body")).strip(),
            }
            for c in (fields.get("comment") or {}).get("comments", [])
        ]
        attachments = [
            {"name": a.get("filename", ""), "size": str(a.get("size", ""))}
            for a in fields.get("attachment") or []
        ]

        return NormalizedTicket(
            external_id=key,
            provider_kind=self.kind,
            title=fields.get("summary", ""),
            work_item_type=issue_type,
            status=status,
            priority=self._map_priority(priority),
            assignee=assignee,
            sprint=self._sprint_name(fields.get("sprint")),
            area_path="",
            epic=self._epic(fields),
            description=_adf_to_text(fields.get("description")).strip(),
            note="",
            url=f"{self.base_url}/browse/{key}" if (self.base_url and key) else "",
            labels=fields.get("labels") or [],
            acceptance_criteria=_split_ac(ac_text),
            acceptance_criteria_html="",
            comments=comments,
            attachments=attachments,
            linked_prs=[],
        )

    @staticmethod
    def _sprint_name(sprint_field: Any) -> str:
        if isinstance(sprint_field, list) and sprint_field:
            last = sprint_field[-1]
            return last.get("name", "") if isinstance(last, dict) else str(last)
        if isinstance(sprint_field, dict):
            return sprint_field.get("name", "")
        return ""

    @staticmethod
    def _epic(fields: dict[str, Any]) -> str:
        """The parent epic — ``parent`` in team-managed projects, the classic
        Epic Link custom field in company-managed ones."""
        parent = fields.get("parent")
        if isinstance(parent, dict):
            summary = (parent.get("fields") or {}).get("summary") or ""
            if summary:
                return summary
        epic_link = fields.get(EPIC_LINK_FIELD)
        return epic_link if isinstance(epic_link, str) else ""

    @staticmethod
    def _map_priority(name: str) -> str:
        lowered = (name or "").lower()
        if lowered in ("highest", "high"):
            return "High"
        if lowered in ("lowest", "low"):
            return "Low"
        return "Medium"

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
                f"{API_PREFIX}/issue/{ticket_external_id}/comment",
                json={"body": _text_to_adf(body)},
            )
            resp.raise_for_status()
            return str(resp.json().get("id", ""))

    def update_status(self, ticket_external_id: str, target_status: str) -> None:
        """Transition the issue by matching the target against its available
        transitions — Jira workflows are per-project, so there is no fixed set."""
        with self._client() as client:
            resp = client.get(f"{API_PREFIX}/issue/{ticket_external_id}/transitions")
            resp.raise_for_status()
            transitions = resp.json().get("transitions", [])
            match = next(
                (t for t in transitions if t.get("name", "").lower() == target_status.lower()),
                None,
            )
            if not match:
                raise ProviderError(f"No Jira transition named '{target_status}' is available")
            resp = client.post(
                f"{API_PREFIX}/issue/{ticket_external_id}/transitions",
                json={"transition": {"id": match["id"]}},
            )
            resp.raise_for_status()

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
        """Create an issue for the test case and relate it to the ticket."""
        if not self.project:
            raise ProviderError("Jira project is not configured")
        body_lines = []
        if precondition:
            body_lines.append(f"Precondition: {precondition}")
        for i, step in enumerate(steps or [], start=1):
            body_lines.append(f"{i}. {step.get('a', '')} -> {step.get('e', '')}")
        description = _text_to_adf("\n".join(body_lines) or title)

        with self._client() as client:

            def _create(issue_type: str) -> httpx.Response:
                return client.post(
                    f"{API_PREFIX}/issue",
                    json={
                        "fields": {
                            "project": {"key": self.project},
                            "summary": title[:250],
                            "description": description,
                            "issuetype": {"name": issue_type},
                        }
                    },
                )

            resp = _create("Test")
            if resp.status_code >= 400:
                # Not every instance defines a 'Test' issue type.
                resp = _create("Task")
            if resp.status_code >= 400:
                raise ProviderError(
                    f"Jira create issue failed ({resp.status_code}): "
                    f"{self._scrub(resp.text[:300])}"
                )
            key = resp.json().get("key", "")

            linked = False
            if link and key:
                linked = (
                    client.post(
                        f"{API_PREFIX}/issueLink",
                        json={
                            "type": {"name": "Relates"},
                            "inwardIssue": {"key": key},
                            "outwardIssue": {"key": ticket_external_id},
                        },
                    ).status_code
                    < 400
                )
        return {
            "external_id": key,
            "url": f"{self.base_url}/browse/{key}" if key else "",
            "status": "To Do",
            "linked": linked,
        }


register(JiraAdapter.kind, JiraAdapter)
