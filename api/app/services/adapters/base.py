"""The provider adapter contract.

Every provider (Azure DevOps / GitHub / Jira) implements :class:`ProviderAdapter`
so that everything above it — connection testing, ticket sync, publishing — stays
provider-agnostic. **This module is a published interface**: the tickets slice
imports it, so signatures here change only with a deliberate contract change.

Adapters talk to the **real** REST APIs over ``httpx``. There is no mock
transport in product code; tests inject one via ``httpx.MockTransport`` through
:meth:`ProviderAdapter.transport`, which is ``None`` everywhere else.

## Secrets

An adapter holds a decrypted PAT for the life of one call. Two rules follow, and
both are enforced here rather than left to each adapter's discretion:

* **Never log it.** No adapter may log its ``secrets``, its auth header, or a
  request it built.
* **Never echo it.** Upstream error text and exception strings go through
  :func:`scrub` before they reach a message, because an adapter cannot know what
  a provider chose to reflect back.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

import httpx

#: What a redacted secret is replaced with in any message that escapes an adapter.
REDACTED = "«redacted»"

#: Shorter than this and a "secret" is almost certainly a placeholder; blanket
#: replacing a 1–3 character string would mangle unrelated error text.
_MIN_SCRUB_LENGTH = 4


class ProviderError(RuntimeError):
    """Adapter configuration or upstream API failure.

    Its ``str()`` reaches API responses and logs, so anything interpolated into
    it must already have been through :func:`scrub`.
    """


def scrub(value: Any, *secrets: str | None) -> str:
    """Render ``value`` as text with every one of ``secrets`` removed.

    Called on every exception string and every upstream response body an adapter
    interpolates into a message. Providers do occasionally reflect a credential
    (a 401 body quoting the token, a redirect carrying it in a query string) and
    an adapter has no way to know in advance, so the removal is unconditional.
    """
    text = str(value)
    for secret in secrets:
        if secret and len(secret) >= _MIN_SCRUB_LENGTH:
            text = text.replace(secret, REDACTED)
    return text


class NormalizedTicket(dict):
    """A provider-agnostic ticket, as a plain ``dict`` subclass.

    Keys — ``external_id`` and ``title`` are always present, the rest are
    optional and default to the empty value of their type:

    ==========================  ==========  ==========================================
    key                         type        meaning
    ==========================  ==========  ==========================================
    ``external_id``             str         provider id: ADO work item id, GitHub
                                            issue number, Jira key. Always a string.
    ``provider_kind``           str         ``azure_devops`` | ``github`` | ``jira``
    ``title``                   str         summary line
    ``work_item_type``          str         User Story / Bug / Task / Issue / Feature
    ``status``                  str         provider-native state name
    ``priority``                str         normalised to High | Medium | Low
    ``assignee``                str         display name or login, "" if unassigned
    ``sprint``                  str         sprint / iteration leaf name
    ``area_path``               str         ADO area path; "" elsewhere
    ``epic``                    str         parent epic name/key, "" if none
    ``description``             str         plain text (HTML/ADF already flattened)
    ``note``                    str         free-form, always "" from adapters
    ``url``                     str         the ticket's web URL
    ``labels``                  list[str]   tags / labels
    ``acceptance_criteria``     list[str]   one entry per criterion
    ``acceptance_criteria_html``str         raw HTML where the provider has it
    ``comments``                list[dict]  ``{who, when, text}``
    ``attachments``             list[dict]  ``{name, size}``
    ``linked_prs``              list[dict]  ``{repo, num, title, status, url}``
    ==========================  ==========  ==========================================

    It is a ``dict`` rather than a dataclass on purpose: consumers persist it
    field-by-field into their own model and a new optional key must not break
    an older consumer.
    """


class ProviderAdapter(ABC):
    """Base class for provider integrations.

    Constructed with a **decrypted** ``secrets`` mapping — building one is the
    job of ``connection_service.adapter_for``, which is the only place the PAT
    is decrypted.
    """

    #: Registry key. Matches ``models.provider_connection`` kinds.
    kind: str = ""

    #: Seconds before any provider request is abandoned. A hung provider must
    #: not hold a hub worker open.
    timeout: float = 30.0

    # -- Optional capabilities --------------------------------------------
    # Declared, not inferred. The optional read methods below default to
    # returning ``[]``, so "this provider has no such concept" is otherwise
    # indistinguishable from "there are none" — tolerable while only sync
    # consumed them, wrong now that an endpoint serves the result to an agent.
    # A caller reads these to tell the two apart; see ``ticket_provider``.
    #: :meth:`fetch_comments` is really implemented.
    supports_comments: bool = False
    #: :meth:`list_test_cases` is really implemented.
    supports_test_cases: bool = False
    #: :meth:`list_test_cases` answers for the whole project, ignoring the
    #: ``ticket_external_id`` hint. True for Azure DevOps.
    test_cases_project_wide: bool = False

    def __init__(
        self,
        config: dict,
        secrets: dict,
        *,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        """
        Args:
            config: non-secret adapter fields (``baseUrl``, ``orgUrl``,
                ``project``, ``org``, ``repo``, ``email``).
            secrets: decrypted secrets. Every kind uses the single key ``pat``.
            transport: an ``httpx`` transport override. **Tests only** — product
                code never passes it, so there is no mock path in the product.
        """
        self.config = config or {}
        self.secrets = secrets or {}
        self.transport = transport

    # -- Connectivity -----------------------------------------------------
    @abstractmethod
    def test_connection(self) -> dict[str, Any]:
        """Verify credentials and reachability.

        Returns ``{ok: bool, message: str, detail: dict}``. Never raises for an
        ordinary failure — an unreachable provider is a ``False``, not an
        exception, because this is what the Test button calls.
        """

    # -- Read -------------------------------------------------------------
    @abstractmethod
    def list_projects(self) -> list[dict[str, Any]]:
        """Connectable projects as ``[{external_id, name, ...}]``."""

    @abstractmethod
    def fetch_tickets(
        self,
        *,
        spec: Any = None,
        ticket_ids: list[str] | None = None,
        include_comments: bool = False,
        project: str | None = None,
    ) -> list[NormalizedTicket]:
        """Fetch and normalise tickets for the given selection.

        **Two ways to say what to pull, and no third.** The
        ``mode``/``sprint``/``area_path``/``states``/``work_item_types`` arguments
        this method used to take are gone: they were a filter language that could
        express a fraction of what a clause query can, and keeping them alongside
        one meant every adapter carried two query builders and had to be told, in a
        comment, not to blend them.

        Args:
            spec: a ``services.ticket_query.TicketQuery`` — the filter. Compiled by
                each adapter into its own dialect (WIQL / JQL / search qualifiers).
                Typed ``Any`` so the adapter layer keeps no import-time dependency
                on the query module.
            ticket_ids: external ids, for pulling *known* work items. Not a filter,
                which is why it is not a clause: the query model has no id field,
                and giving it one would make a list pretend to be a query. Ignored
                when ``spec`` is given.
            include_comments: ``False`` for bulk sync — comments cost one extra
                request per ticket, an N+1 that makes a sprint sync crawl. The
                detail view loads them lazily via :meth:`fetch_comments`.
            project: override the connection's configured default project.
                Providers with no project concept ignore it.

        With neither ``spec`` nor ``ticket_ids``, an adapter returns everything in
        the project it can see. Callers are expected to require one of the two — see
        ``routers.tickets.SyncRequest`` — because "everything" is a decision worth
        making explicitly rather than by omission.
        """

    def count_tickets(self, *, spec: Any = None, project: str | None = None) -> int:
        """How many work items a query matches, without reading their fields.

        Separate from :meth:`fetch_tickets` because that one is **capped**
        (``MAX_SYNC_ITEMS``) so a bulk sync cannot hang, and a capped number is the
        wrong answer to "how many are there" — it silently reads as the truth. A
        provider that can count cheaply overrides this; the default falls back to
        counting what a fetch returns, and so inherits that cap.
        """
        return len(self.fetch_tickets(spec=spec, project=project, include_comments=False) or [])

    def fetch_comments(self, ticket_external_id: str) -> list[dict[str, Any]]:
        """One ticket's comments, on demand, as ``[{who, when, text}]``.

        Overriders must set :attr:`supports_comments` and **must raise**
        :class:`ProviderError` when the provider call fails, rather than
        returning ``[]``. Sync may swallow a comment failure — comments are
        decoration on a work item and a scope-less PAT must not fail a whole
        sync — but this method answers a caller who asked for comments and
        nothing else, and an empty list would tell it there are none.
        """
        return []

    def list_sprints(self) -> list[dict[str, Any]]:
        """Sprints/iterations as ``[{id, name, path, start_date, finish_date}]``.

        ``path`` is what :meth:`fetch_tickets` wants as ``sprint_path``. Default
        empty — a provider without iterations does not have to override.
        """
        return []

    def list_work_item_metadata(self) -> dict[str, Any]:
        """Everything a filter picker needs about the connected project.

        ``work_item_types`` carries each type's **own** states, because a Bug and a
        User Story do not share a state set. ``area_paths`` / ``iteration_paths``
        are flattened pre-order with a ``depth``, so a picker can indent them
        without walking a tree.
        """
        return {
            "area_paths": [],
            "iteration_paths": [],
            "work_item_types": [],
            "states": [],
            "members": [],
            "tags": [],
            "epics": [],
        }

    def list_repos(self) -> list[dict[str, Any]]:
        """Git repositories as ``[{name, clone_url, web_url, default_branch}]``."""
        return []

    def list_test_cases(self, ticket_external_id: str | None = None) -> list[dict[str, Any]]:
        """Existing test cases as ``[{external_id, title, state}]``.

        ``ticket_external_id`` is a *hint*, not a guarantee: Azure DevOps has no
        cheap per-work-item query for this and answers project-wide, which is
        what its consumer (continuing existing numbering when generating) needs
        anyway. Callers must not assume the result is scoped.

        Overriders must set :attr:`supports_test_cases` and raise
        :class:`ProviderError` on failure — see :meth:`fetch_comments`.
        """
        return []

    # -- Write ------------------------------------------------------------
    @abstractmethod
    def publish_comment(
        self,
        ticket_external_id: str,
        body: str,
        *,
        attachments: list[str] | None = None,
    ) -> str:
        """Post a comment on the work item. Returns the external comment id."""

    def update_status(self, ticket_external_id: str, target_status: str) -> None:
        """Transition the work item.

        **Raises by default rather than doing nothing.** A silent no-op reports
        success for a transition that never happened, and a caller then records a
        status the provider does not have — which is worse than a clean failure.
        Every shipped adapter overrides this; a provider with no workflow should
        say so here.
        """
        raise ProviderError(
            f"Transitioning a work item is not supported for '{self.kind or 'this provider'}'"
        )

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
        """Create a provider-side test case and optionally link it to the ticket.

        ``steps`` entries are ``{"a": action, "e": expected}``. Returns
        ``{external_id, url, status, linked}``. Raises :class:`ProviderError`
        by default — not every provider has the concept.
        """
        raise ProviderError("Creating test cases is not supported for this provider")

    # -- Internals --------------------------------------------------------
    def _http(self, **kwargs: Any) -> httpx.Client:
        """Build the adapter's ``httpx`` client, honouring the test transport.

        Every adapter constructs its client through here so the timeout is
        applied once and the transport override has exactly one entry point.
        """
        kwargs.setdefault("timeout", self.timeout)
        if self.transport is not None:
            kwargs["transport"] = self.transport
        return httpx.Client(**kwargs)
