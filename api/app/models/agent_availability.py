"""Whether an agent in the suite is open to users, or still "coming soon" (#186).

## Why this is not a config value

Every other agent knob — the URL, the audience, whether SSO can work — is
environment configuration, read once at boot. Availability is different in kind:
it is a *product* decision an admin makes and unmakes, and the point of making it
a row is that flipping it takes effect for the next request rather than the next
deploy.

## Why it is not ``Product.live``

``Product.live`` drives the ``Live`` / ``Placeholder`` badge and is design copy,
not runtime state — D-Agent stays a placeholder even once a URL is configured for
it. Conflating the two would mean a marketing badge changed the moment an admin
toggled availability, and vice versa.

## Absent means available

There is no row until somebody turns an agent off, and a missing row reads as
enabled. A table that had to be seeded before the suite worked would be a new way
for a fresh install to come up broken, and the safe default for "is this product
open?" is the state the suite has always been in.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base, timestamp_column


class AgentAvailability(Base):
    __tablename__ = "agent_availability"

    #: The agent's audience (``qagent`` / ``dagent``) — the same discriminator the
    #: token audience and the launch registry already use, so there is one name
    #: for an agent across the hub rather than a second vocabulary here.
    key: Mapped[str] = mapped_column(String(32), primary_key=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    updated_at: Mapped[datetime] = timestamp_column()
    #: Who last flipped it. Nullable and ``SET NULL``: the audit trail of *what*
    #: the setting is must survive the deletion of the account that set it.
    updated_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
