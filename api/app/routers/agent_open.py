"""``GET /agents/{key}/open`` — is this product available? (#186)

**The one deliberately public thing about agents.** The edge proxy asks this
before letting a browser through to an agent, and that browser may be a
stranger's: someone following a link to a product that is not open yet has no hub
session, so requiring one would mean the gate could not run for exactly the people
it exists for.

Its own module, and its own read-only path, for two reasons that are really one:

* ``ROUTERS`` in ``main.py`` assigns a posture per router, and ``agents`` is
  ``PROTECTED`` — the launch registry is the hub UI's own. Reaching in to make one
  route public would have meant relaxing the whole router.
* ``security.py`` allowlists by **path**, not by method. Had this read shared a
  path with the admin toggle, that path would be public at the backstop layer, and
  the backstop exists precisely to survive the route dependency being wrong.

Nothing here is a secret: the answer is the sentence the coming-soon page the
caller is about to see says out loud, and it says nothing about the agent, the
workspace or the caller.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.orm import Session

from app.db import get_db
from app.schemas import AgentAvailabilityOut
from app.services import agent_availability_service

router = APIRouter(tags=["agents"])


def _register(key: str) -> None:
    """Register one agent's read at a STATIC path.

    Not ``/agents/{key}/open`` with a path parameter, because the allowlist in
    ``security.py`` is matched exactly and the wiring test asks
    ``is_public(route.path)`` — a template would be a route that is neither
    allowlisted nor guarded, which is precisely the hole that test exists to
    catch. Static paths make the route, the allowlist entry and the runtime URL
    the same string, so there is nothing to keep in sync by hand.

    A key with no route is therefore refused by the guard before routing, which is
    the stricter answer: an unknown name cannot even probe for existence.
    """

    @router.get(f"/agents/{key}/open", response_model=AgentAvailabilityOut, name=f"agent_open_{key}")
    def _read(response: Response, db: Session = Depends(get_db)) -> AgentAvailabilityOut:  # noqa: ANN202
        enabled = agent_availability_service.is_enabled(db, key)
        # 403 when closed, because the STATUS is the answer for this endpoint's one
        # consumer: nginx `auth_request` reads status codes and cannot parse a body
        # (that needs njs). A 200 saying `enabled: false` would be a gate that
        # always opens — the failure mode being avoided is precisely a switch that
        # looks wired and is not.
        #
        # The body is still there for a human with curl, so the endpoint explains
        # itself rather than answering a bare 403.
        if not enabled:
            response.status_code = status.HTTP_403_FORBIDDEN
        return AgentAvailabilityOut(key=key, enabled=enabled)


for _key in agent_availability_service.GATEABLE_AGENTS:
    _register(_key)
