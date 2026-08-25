"""Reading and writing whether an agent is open to users (#186).

One place decides what "enabled" means, because three callers ask: the launch
registry the hub's own UI reads, the admin toggle that writes it, and the
unauthenticated check the edge proxy makes before letting a browser through to an
agent. Three copies of "absent means available" would eventually disagree, and the
one that disagreed would be the edge — the only one a user meets before anything
else can explain itself.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.agent_availability import AgentAvailability

#: The agents this hub can gate, by token audience — the same discriminator the
#: launch registry and the token audiences already use.
GATEABLE_AGENTS = ("qagent", "dagent")


def is_enabled(db: Session, key: str) -> bool:
    """Whether ``key`` is open to users. Unknown or unset ⇒ True.

    An unknown key answers True on purpose: this function gates access, and a
    typo in a route or an agent the hub has not heard of must not become an
    outage. The admin write below is where an unknown key is refused, because
    that is where being wrong is cheap and visible.
    """
    row = db.get(AgentAvailability, key)
    return True if row is None else bool(row.enabled)


def all_enabled(db: Session) -> dict[str, bool]:
    """``{key: enabled}`` for every gateable agent, defaults included."""
    rows = {r.key: bool(r.enabled) for r in db.query(AgentAvailability).all()}
    return {key: rows.get(key, True) for key in GATEABLE_AGENTS}


def set_enabled(db: Session, key: str, enabled: bool, *, actor_id: int | None) -> bool:
    """Turn ``key`` on or off. Returns the stored value. Caller commits."""
    row = db.get(AgentAvailability, key)
    if row is None:
        row = AgentAvailability(key=key)
        db.add(row)
    row.enabled = enabled
    row.updated_by = actor_id
    return bool(row.enabled)
