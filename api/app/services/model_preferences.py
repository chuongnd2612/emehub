"""Which Claude model and effort level a member's runs use.

The hub owns this because it owns the identity the preference hangs off — the
same reason it owns the credential. It is also the one place that can *act* on
it: knowledge builds are the hub's own Claude work (ADR 0007), so
:func:`resolve_for_run` is called by :mod:`app.services.claude_cli` on every
invocation, and picking a model here changes what the next build runs on.

## Absent means "the system default"

Empty columns, and a missing row, both resolve to ``settings.claude_model`` and
:data:`DEFAULT_EFFORT`. Same shape as ``agent_availability``, where an absent row
means enabled — and the reason shipping this table changed nobody's builds: a
member's model only moves once they choose one.

There is deliberately no second config key for the effort. One deploy-time knob
(``EMEHUB_CLAUDE_MODEL``) sets the workspace's answer; the rest is either a
member's choice or a constant here.

There is also deliberately no *fast* model. One was stored here briefly (#190)
and read by nothing: the hub makes exactly one kind of Claude call, a knowledge
build, so there was no cheaper second invocation to route it to. It was removed
(#197) rather than left as a control that decides nothing.

## The known sets are enforced here

``KNOWN_MODELS`` and ``EFFORT_LEVELS`` are the one place a preference is
validated. A stored value naming something the CLI does not accept would fail at
the far end of a build, minutes later, with an error nobody can trace back to a
dropdown — so it is refused at the write, while the user is still looking at the
control. ``EFFORT_LEVELS`` matches ``claude --effort`` exactly; an unknown value
there is only a warning to the CLI, which would silently ignore the setting.

The *labels* live in the SPA (``app/src/screens/Claude/state.ts``) because they
are display copy. Duplicating them here would create a second place to update and
a way for the two to disagree about what a model is called.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.config import settings
from app.models.model_preferences import UserModelPreferences

#: Every model id a preference may name. Ordered as the picker orders them.
KNOWN_MODELS: tuple[str, ...] = (
    "claude-opus-5",
    "claude-sonnet-5",
    "claude-haiku-4-5",
)

#: ``claude --effort`` levels, verbatim. The CLI warns and falls back to its own
#: default on anything else, which would make a chosen setting quietly do
#: nothing — so the hub refuses the write instead.
EFFORT_LEVELS: tuple[str, ...] = ("low", "medium", "high", "xhigh", "max")

#: The workspace's effort when nobody has chosen. Mid-range on purpose: the hub's
#: only Claude work is a knowledge build, which traverses a whole repository.
DEFAULT_EFFORT = "high"


class UnknownModelError(ValueError):
    """A preference named a model id the hub does not recognise."""


class UnknownEffortError(ValueError):
    """A preference named an effort level the Claude CLI does not accept."""


def _defaults() -> dict[str, str]:
    """What a user with no choices gets."""
    return {
        "mainModel": settings.claude_model,
        "effort": DEFAULT_EFFORT,
    }


def get(db: Session, user_id: int | None) -> dict[str, object]:
    """``user_id``'s effective preferences, falling back **field by field**.

    Field by field rather than row-or-nothing: a row written before a column
    existed, or one whose column is blank, must still yield a usable value rather
    than an empty string the CLI would choke on. ``user_id=None`` — work with no
    attributable owner — gets the defaults, never somebody else's choices.

    ``usingDefaults`` says whether any of this is actually the user's doing. The
    screen needs it to avoid the worst version of this control: showing a model
    the user never picked as though they had. It is *not* derivable from the
    values — the default and a deliberate choice of the same model are identical
    on the wire.
    """
    out: dict[str, object] = dict(_defaults())
    row = None if user_id is None else db.get(UserModelPreferences, user_id)
    if row is not None:
        if row.main_model:
            out["mainModel"] = row.main_model
        if row.effort:
            out["effort"] = row.effort
    out["usingDefaults"] = row is None or not (row.main_model or row.effort)
    return out


def resolve_for_run(db: Session, owner_id: int | None) -> tuple[str, str]:
    """``(model, effort)`` for one Claude CLI invocation on ``owner_id``'s behalf.

    The whole point of the preference resource: this is what makes it decide
    something. ``owner_id`` is the owner of the work being done — the knowledge
    row's owner, not the caller — so a build spends the model its owner chose.

    ``owner_id=None`` is the shared namespace (an unattributed row, a background
    re-index) and resolves to the system default. There is nobody to ask, and
    inheriting whichever member happened to trigger it would be worse than a
    predictable answer.
    """
    prefs = get(db, owner_id)
    return str(prefs["mainModel"]), str(prefs["effort"])


def set_preferences(
    db: Session, user_id: int, *, main_model: str, effort: str
) -> dict[str, object]:
    """Store the whole preference and return the full new state. Caller commits.

    Everything is validated before anything is written, so a bad ``effort``
    cannot leave a half-applied model behind.
    """
    if main_model not in KNOWN_MODELS:
        raise UnknownModelError(main_model)
    if effort not in EFFORT_LEVELS:
        raise UnknownEffortError(effort)

    row = db.get(UserModelPreferences, user_id)
    if row is None:
        row = UserModelPreferences(user_id=user_id)
        db.add(row)
    row.main_model = main_model
    row.effort = effort
    # Always False: a write IS the choice, so the caller renders the result of
    # this request without having to re-read to find out whose values they are.
    return {
        "mainModel": row.main_model,
        "effort": row.effort,
        "usingDefaults": False,
    }
