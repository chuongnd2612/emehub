"""``/me/model-preferences`` — the model and effort a member's runs use.

## Deliberately not part of the integration contract

This lives under ``/me`` because it is *about* the calling user, not because it
belongs with :mod:`app.routers.me`. That module is the contract QAgent and DAgent
consume and returns exactly ``id, email, name, role`` (INTEGRATION.md §3);
widening it for a settings screen would be a cross-repo change for a UI
convenience. This router is registered ``PROTECTED`` instead — ``aud: "emehub"``
only, so an agent token is refused — and is therefore absent from
INTEGRATION.md and free to change shape without an issue in two other repos.

When an agent does need to know which model to run with, that is a contract
addition and gets its own review.

## It is not a display setting

What is stored here is read by :func:`app.services.model_preferences.resolve_for_run`
on every hub-run Claude CLI invocation — which today means knowledge builds, the
one piece of domain work the hub owns (ADR 0007). Picking a model changes what
the next build runs on.

## Shape

``PUT`` returns the **full** new state rather than an ack, matching every other
mutation the SPA calls (``PUT /credentials/claude/mode``, ``PUT
/agents/{key}/availability``): the client renders the hub's answer instead of
assuming its own optimistic value was accepted.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps_auth import require_user
from app.models.user import User
from app.schemas import ApiModel
from app.services import model_preferences
from app.services.model_preferences import UnknownEffortError, UnknownModelError

router = APIRouter(prefix="/me", tags=["preferences"])


# ---------------------------------------------------------------- schemas
class ModelPreferencesOut(ApiModel):
    """Model **ids**, never display labels — the SPA owns the copy."""

    main_model: str
    #: A ``claude --effort`` level: low | medium | high | xhigh | max.
    effort: str
    #: True when the user has chosen nothing and these are the workspace
    #: defaults. The screen says so rather than presenting them as a choice.
    using_defaults: bool = False


class ModelPreferencesIn(ApiModel):
    main_model: str
    effort: str


# ---------------------------------------------------------------- routes
@router.get("/model-preferences", response_model=ModelPreferencesOut)
def get_model_preferences(
    user: User = Depends(require_user), db: Session = Depends(get_db)
) -> ModelPreferencesOut:
    """The caller's effective preferences, flagged if they are just the defaults."""
    return ModelPreferencesOut(**model_preferences.get(db, user.id))


@router.put("/model-preferences", response_model=ModelPreferencesOut)
def set_model_preferences(
    body: ModelPreferencesIn,
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
) -> ModelPreferencesOut:
    """Store the whole preference. An unknown value is refused rather than saved.

    400, not 422: the values are well-formed, they just name a model or an effort
    level that does not exist — and the message says which, because the
    alternative is a build failing minutes later with nothing pointing back at
    this control. An unknown effort matters especially: the CLI only *warns* and
    carries on with its own default, so storing one would leave a setting that
    silently does nothing.
    """
    try:
        state = model_preferences.set_preferences(
            db,
            user.id,
            main_model=body.main_model,
            effort=body.effort,
        )
    except UnknownModelError as exc:
        raise HTTPException(status_code=400, detail=f"Unknown model: {exc}") from exc
    except UnknownEffortError as exc:
        raise HTTPException(status_code=400, detail=f"Unknown effort level: {exc}") from exc
    db.commit()
    return ModelPreferencesOut(**state)
