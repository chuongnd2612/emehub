"""ORM models.

Importing this package registers every model on ``app.db.Base.metadata`` — the
Alembic env imports it so autogenerate sees the full schema.
"""

from app.models.audit import AuditLog  # noqa: F401
from app.models.session import Session  # noqa: F401
from app.models.ticket import Ticket  # noqa: F401
from app.models.user import User  # noqa: F401

__all__ = ["AuditLog", "Session", "Ticket", "User"]
