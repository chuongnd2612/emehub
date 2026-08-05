"""``GET /agents`` — the launch registry the hub's own UI reads.

Deliberately **not** part of the agent contract: it is `aud: "emehub"`-only, so
an agent token is refused. An agent has no business enumerating its siblings, and
keeping this out of INTEGRATION.md means it can change shape without a cross-repo
issue.

Equally deliberately not folded into ``GET /me``: that *is* a contract endpoint
returning exactly ``id, email, name, role``, and the registry has nothing to do
with the calling principal. Widening ``/me`` for a UI convenience would ship a
contract change for no reason.

The distinction this endpoint exists to express is ``registered`` vs
``handoffReady`` — see :meth:`app.config.Settings.handoff_ready`. An agent can be
registered (a URL is configured, so the hub mints it tokens) while single sign-on
still cannot work, because the refresh cookie will never reach its origin. The UI
needs to tell those apart to avoid offering a launch that silently fails.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.config import AUDIENCE_DAGENT, AUDIENCE_QAGENT, settings
from app.deps_auth import require_user
from app.models.user import User
from app.schemas import AgentListOut, AgentOut

router = APIRouter(tags=["agents"])

#: Display metadata for each agent audience. ``key`` is the short discriminator
#: the frontend already uses for per-product theming (``q`` / ``d``).
AGENTS: tuple[tuple[str, str, str], ...] = (
    (AUDIENCE_QAGENT, "q", "Q-Agent"),
    (AUDIENCE_DAGENT, "d", "D-Agent"),
)


@router.get("/agents", response_model=AgentListOut)
def list_agents(_: User = Depends(require_user)) -> AgentListOut:
    out = [
        AgentOut(
            id=audience,
            key=key,
            name=name,
            url=settings.agent_url(audience) or None,
            registered=audience in settings.registered_audiences,
            handoff_ready=settings.handoff_ready(audience),
            reason=settings.handoff_blocker(audience),
        )
        for audience, key, name in AGENTS
    ]
    return AgentListOut(agents=out)
