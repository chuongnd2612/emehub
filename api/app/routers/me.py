"""``GET /me`` — the identity endpoint agents consume (INTEGRATION.md §3).

Deliberately separate from ``/auth/me``: that one serves the hub's own SPA and
may grow UI-shaped fields, while this is a contract with QAgent and DAgent and
returns exactly ``id, email, name, role``. Changing its shape requires an
INTEGRATION.md update and a matching issue in both agent repos
(CLAUDE.md › Cross-repo rule).

It uses :func:`require_principal`, so an agent may call it with the token it
holds (``aud: "qagent"`` / ``"dagent"``) rather than having to obtain a hub
token. Hub *management* endpoints stay ``aud: "emehub"``-only.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.deps_auth import require_principal
from app.models.user import User
from app.schemas import MeOut

router = APIRouter(tags=["identity"])


@router.get("/me", response_model=MeOut)
def me(user: User = Depends(require_principal)) -> MeOut:
    return MeOut(
        id=user.id,
        email=user.email,
        name=user.full_name,
        first_name=user.first_name,
        last_name=user.last_name,
        role=user.role,
    )
