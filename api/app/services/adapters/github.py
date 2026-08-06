"""GitHub adapter — issues as work items, plus repository discovery.

Talks to the real GitHub REST API over ``httpx``, authenticating with a personal
access token as a bearer.

Config: ``org`` (owner or organisation login), ``repo`` (repository name),
``baseUrl`` (GitHub Enterprise API base — omit for github.com).
Secret: ``pat``.

Three normalisation behaviours come from DAgent's ``lib/github.ts``, which reads
issues more carefully than QAgent's adapter did:

* the work item **type** comes from the labels (bug / feature / epic) instead of
  being hardcoded to "Issue";
* the **status** honours the widespread ``status: X`` label convention, because
  GitHub issues have no workflow field of their own — only open/closed;
* **acceptance criteria** are lifted from the body's ``- [ ]`` checklist, which
  is how GitHub users actually write them.
"""

from __future__ import annotations

import re
from typing import Any

import httpx

from app.services.adapters import register
from app.services.adapters.base import (
    NormalizedTicket,
    ProviderAdapter,
    ProviderError,
    scrub,
)
from app.services.gh_search import build_search, sort_params

PUBLIC_API_BASE = "https://api.github.com"
API_VERSION = "2022-11-28"

_PER_PAGE = 100
#: The ``status: In Review`` label convention — the only honest source of a
#: richer status than open/closed.
_STATUS_LABEL = re.compile(r"^status:\s*", re.IGNORECASE)
#: A markdown task-list item: ``- [ ] the thing`` / ``* [x] the thing``.
_CHECKLIST_ITEM = re.compile(r"^\s*[-*]\s*\[[ xX]\]\s*(.+)$")


def _label_names(labels: list[Any]) -> list[str]:
    """Label names, whether GitHub returned objects or bare strings."""
    out = []
    for label in labels or []:
        name = label.get("name", "") if isinstance(label, dict) else str(label)
        if name:
            out.append(name)
    return out


def _title_case(value: str) -> str:
    return " ".join(word[:1].upper() + word[1:] for word in value.split())


def _type_from_labels(labels: list[str]) -> str:
    lowered = [label.lower() for label in labels]
    if any("bug" in label for label in lowered):
        return "Bug"
    if any("feature" in label or "enhancement" in label for label in lowered):
        return "Feature"
    if any("epic" in label for label in lowered):
        return "Epic"
    return "Issue"


def _status_from_issue(state: str, labels: list[str]) -> str:
    """A ``status: X`` label if the repo uses that convention, else open/closed."""
    for label in labels:
        if _STATUS_LABEL.match(label):
            resolved = _title_case(_STATUS_LABEL.sub("", label).strip())
            if resolved:
                return resolved
    return "Done" if state == "closed" else "In Progress"


def _criteria_from_body(body: str) -> list[str]:
    """Acceptance criteria from the body's markdown checklist."""
    criteria = []
    for line in (body or "").splitlines():
        match = _CHECKLIST_ITEM.match(line)
        if match:
            criteria.append(match.group(1).strip())
    return criteria


class GitHubAdapter(ProviderAdapter):
    kind = "github"
    supports_comments = True
    # GitHub issues have no test-case concept. ``list_test_cases`` is left at the
    # base default, and the flag is what stops [] reading as "none exist".
    supports_test_cases = False

    def __init__(self, config: dict, secrets: dict, *, transport=None) -> None:
        super().__init__(config, secrets, transport=transport)
        self.org = (self.config.get("org") or "").strip()
        self.repo = (self.config.get("repo") or "").strip()
        self.pat = self.secrets.get("pat") or ""
        self.api_base = self._api_base(self.config.get("baseUrl") or self.config.get("orgUrl"))

    @staticmethod
    def _api_base(raw: str | None) -> str:
        """Resolve the REST base: github.com by default, else the Enterprise host.

        A GitHub Enterprise Server install serves its REST API at
        ``https://host/api/v3``; accept either that full path or the bare host
        and append the suffix, so an operator can paste whichever they have.
        """
        base = (raw or "").strip().rstrip("/")
        if not base:
            return PUBLIC_API_BASE
        if "github.com" in base:
            return PUBLIC_API_BASE
        if base.endswith("/api/v3"):
            return base
        return f"{base}/api/v3"

    def _client(self) -> httpx.Client:
        if not self.pat:
            raise ProviderError("GitHub PAT is not configured")
        return self._http(
            base_url=self.api_base,
            headers={
                "Authorization": f"Bearer {self.pat}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": API_VERSION,
            },
        )

    def _require_repo(self) -> tuple[str, str]:
        if not (self.org and self.repo):
            raise ProviderError("GitHub org/repo is not configured")
        return self.org, self.repo

    def _scrub(self, value: Any) -> str:
        return scrub(value, self.pat)

    # -- Connectivity -----------------------------------------------------
    def test_connection(self) -> dict[str, Any]:
        try:
            with self._client() as client:
                resp = client.get("/user")
                resp.raise_for_status()
                login = resp.json().get("login", "")
            return {
                "ok": True,
                "message": f"Connected to GitHub as {login}",
                "detail": {"login": login},
            }
        except ProviderError as exc:
            return {"ok": False, "message": str(exc), "detail": {}}
        except httpx.HTTPStatusError as exc:
            return {
                "ok": False,
                "message": f"GitHub returned {exc.response.status_code}",
                "detail": {"statusCode": exc.response.status_code},
            }
        except httpx.HTTPError as exc:
            return {
                "ok": False,
                "message": f"GitHub connection failed: {self._scrub(exc)}",
                "detail": {},
            }

    # -- Read -------------------------------------------------------------
    def list_projects(self) -> list[dict[str, Any]]:
        """GitHub has no project concept matching ADO/Jira — report the repo."""
        if not (self.org and self.repo):
            return []
        with self._client() as client:
            resp = client.get(f"/repos/{self.org}/{self.repo}")
            resp.raise_for_status()
            data = resp.json()
        return [{"external_id": str(data.get("id", "")), "name": data.get("full_name", self.repo)}]

    def list_repos(self) -> list[dict[str, Any]]:
        """Repositories owned by the configured account.

        ``org`` may be a GitHub *organisation* or a *personal* account;
        :meth:`_discover_owner_repos` covers both. With no owner configured,
        falls back to the single configured repository.
        """
        with self._client() as client:
            if self.org:
                items = self._discover_owner_repos(client, self.org)
            elif self.repo:
                resp = client.get(f"/repos/{self.repo}")
                resp.raise_for_status()
                items = [resp.json()]
            else:
                return []
        return [
            {
                "name": r.get("name", ""),
                "clone_url": r.get("clone_url", ""),
                "web_url": r.get("html_url", ""),
                "default_branch": r.get("default_branch", ""),
            }
            for r in items
        ]

    def _discover_owner_repos(self, client: httpx.Client, owner: str) -> list[dict[str, Any]]:
        """Repositories owned by ``owner``, organisation or personal account.

        Each step covers a case the previous one misses:

        1. ``/orgs/{owner}/repos`` — organisations only, but includes private
           repos for members.
        2. that 404s for a *personal* account, so fall back to ``/user/repos``
           (which also sees private repos the PAT can reach) filtered to ``owner``.
        3. last resort, the single configured repo — the case of a PAT scoped to
           exactly one repository.
        """
        resp = client.get(
            f"/orgs/{owner}/repos", params={"per_page": _PER_PAGE, "sort": "full_name"}
        )
        if resp.status_code < 400:
            return resp.json()

        resp = client.get(
            "/user/repos",
            params={
                "per_page": _PER_PAGE,
                "sort": "full_name",
                "affiliation": "owner,collaborator,organization_member",
            },
        )
        if resp.status_code < 400:
            mine = [
                r
                for r in resp.json()
                if ((r.get("owner") or {}).get("login") or "").lower() == owner.lower()
            ]
            if mine:
                return mine

        if self.repo:
            single = client.get(f"/repos/{owner}/{self.repo}")
            single.raise_for_status()
            return [single.json()]

        resp.raise_for_status()
        return []

    def count_tickets(self, *, spec: Any = None, project: str | None = None) -> int:
        """The real total, from the search API's own ``total_count``.

        Separate from :meth:`fetch_tickets` because that one takes a page, and a page
        size is the wrong answer to "how many are there". With no query to compile
        there is nothing cheaper than the base class's fetch-and-count.
        """
        if spec is None:
            return super().count_tickets(spec=spec, project=project)
        org, repo = self._require_repo()
        with self._client() as client:
            resp = client.get(
                "/search/issues",
                params={"q": build_search(spec, org=org, repo=repo), "per_page": 1},
            )
            resp.raise_for_status()
            return int(resp.json().get("total_count", 0))

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
        project: str | None = None,  # GitHub has no project concept; unused
        spec: Any = None,
    ) -> list[NormalizedTicket]:
        org, repo = self._require_repo()
        with self._client() as client:
            if spec is not None:
                # The compiled query replaces the legacy selection outright; mixing
                # them would silently re-apply a condition the user had removed.
                issues = self._search_issues(client, spec, org=org, repo=repo)
            elif mode == "selected" and ticket_ids:
                issues = [self._get_issue(client, num) for num in ticket_ids]
                issues = [i for i in issues if i]
            else:
                params: dict[str, Any] = {"state": "open", "per_page": _PER_PAGE}
                if mode == "assigned":
                    params["assignee"] = self._current_login(client)
                resp = client.get(f"/repos/{org}/{repo}/issues", params=params)
                resp.raise_for_status()
                # The issues endpoint also returns pull requests.
                issues = [i for i in resp.json() if "pull_request" not in i]
            return [
                self._normalize(client, issue, include_comments=include_comments)
                for issue in issues
            ]

    def _search_issues(
        self, client: httpx.Client, spec: Any, *, org: str, repo: str
    ) -> list[dict[str, Any]]:
        """Run a compiled query through ``GET /search/issues``.

        A different endpoint from the legacy path on purpose: ``/repos/…/issues`` has
        no query language at all, which is why the old adapter silently ignored
        ``states``/``types``/``area``. The search API is the only one that can honour
        a clause.

        Two of its limits are real and worth knowing rather than hiding: it returns
        at most 1000 results however you page, and its objects are issue payloads
        that carry everything :meth:`_normalize` reads. ``is:issue`` in the compiled
        ``q`` is what keeps pull requests out.
        """
        params = {
            "q": build_search(spec, org=org, repo=repo),
            "per_page": _PER_PAGE,
            **sort_params(spec),
        }
        resp = client.get("/search/issues", params=params)
        if resp.status_code == 422:
            # The search API's way of saying the query was malformed. Surfacing its
            # own message beats "no results", which is what a caller would otherwise
            # read this as.
            raise ProviderError(
                f"GitHub rejected the search: {self._scrub(resp.text[:300])}"
            )
        resp.raise_for_status()
        return [i for i in resp.json().get("items", []) if "pull_request" not in i]

    def fetch_comments(self, ticket_external_id: str) -> list[dict[str, Any]]:
        """This issue's comments. Raises rather than hiding a provider failure.

        A non-200 used to read as "no comments", which is wrong for a caller that
        asked for comments and nothing else.
        """
        org, repo = self._require_repo()
        with self._client() as client:
            try:
                resp = client.get(f"/repos/{org}/{repo}/issues/{ticket_external_id}/comments")
            except httpx.HTTPError as exc:
                raise ProviderError(f"GitHub is unreachable: {scrub(exc, self.pat)}") from exc
            if resp.status_code != 200:
                raise ProviderError(
                    f"GitHub rejected the comment read for issue {ticket_external_id} "
                    f"(HTTP {resp.status_code})"
                )
            return self._comments(resp.json())

    @staticmethod
    def _comments(payload: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [
            {
                "who": (c.get("user") or {}).get("login", ""),
                "when": c.get("created_at", ""),
                "text": c.get("body") or "",
            }
            for c in payload
        ]

    def _current_login(self, client: httpx.Client) -> str:
        resp = client.get("/user")
        resp.raise_for_status()
        return resp.json().get("login", "")

    def _get_issue(self, client: httpx.Client, number: str) -> dict[str, Any] | None:
        resp = client.get(f"/repos/{self.org}/{self.repo}/issues/{number}")
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        return resp.json()

    # -- Normalisation ----------------------------------------------------
    def _normalize(
        self, client: httpx.Client, issue: dict[str, Any], *, include_comments: bool = False
    ) -> NormalizedTicket:
        number = issue.get("number")
        labels = _label_names(issue.get("labels", []))
        assignee = (issue.get("assignee") or {}).get("login", "")
        body = issue.get("body") or ""

        comments: list[dict[str, Any]] = []
        if include_comments and issue.get("comments", 0):
            resp = client.get(f"/repos/{self.org}/{self.repo}/issues/{number}/comments")
            if resp.status_code == 200:
                comments = self._comments(resp.json())

        return NormalizedTicket(
            external_id=str(number),
            provider_kind=self.kind,
            title=issue.get("title", ""),
            work_item_type=_type_from_labels(labels),
            status=_status_from_issue(issue.get("state", ""), labels),
            priority=self._map_priority(labels),
            assignee=assignee,
            sprint="",
            area_path=f"{self.org}/{self.repo}" if self.org and self.repo else "",
            epic="",
            description=body.strip(),
            note="",
            url=issue.get("html_url", ""),
            labels=labels,
            acceptance_criteria=_criteria_from_body(body),
            acceptance_criteria_html="",
            comments=comments,
            attachments=[],
            linked_prs=[],
        )

    @staticmethod
    def _map_priority(labels: list[str]) -> str:
        lowered = [label.lower() for label in labels]
        if any(
            "high" in label or "critical" in label or "urgent" in label for label in lowered
        ):
            return "High"
        if any("low" in label for label in lowered):
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
        org, repo = self._require_repo()
        with self._client() as client:
            resp = client.post(
                f"/repos/{org}/{repo}/issues/{ticket_external_id}/comments",
                json={"body": body},
            )
            resp.raise_for_status()
            return str(resp.json().get("id", ""))

    def update_status(self, ticket_external_id: str, target_status: str) -> None:
        """Open or close the issue. GitHub has no richer native workflow."""
        org, repo = self._require_repo()
        state = "closed" if target_status.strip().lower() in ("done", "closed") else "open"
        with self._client() as client:
            resp = client.patch(
                f"/repos/{org}/{repo}/issues/{ticket_external_id}", json={"state": state}
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
        """Create an issue for the test case, referencing the source issue."""
        org, repo = self._require_repo()
        lines = [f"**Priority:** {priority}"]
        if precondition:
            lines.append(f"**Precondition:** {precondition}")
        for i, step in enumerate(steps or [], start=1):
            lines.append(f"{i}. {step.get('a', '')} — _{step.get('e', '')}_")
        if link:
            lines.append(f"\nTest case for #{ticket_external_id}")
        with self._client() as client:
            resp = client.post(
                f"/repos/{org}/{repo}/issues",
                json={
                    "title": f"[Test] {title}",
                    "body": "\n".join(lines),
                    "labels": ["qa", "test-case"],
                },
            )
            if resp.status_code >= 400:
                raise ProviderError(
                    f"GitHub create issue failed ({resp.status_code}): "
                    f"{self._scrub(resp.text[:300])}"
                )
            issue = resp.json()
        return {
            "external_id": str(issue.get("number", "")),
            "url": issue.get("html_url", ""),
            "status": "Open",
            "linked": bool(link),
        }


register(GitHubAdapter.kind, GitHubAdapter)
