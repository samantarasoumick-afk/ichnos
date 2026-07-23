import uuid

from sqlalchemy import Column
from sqlalchemy import DateTime
from sqlalchemy import ForeignKey
from sqlalchemy import String
from sqlalchemy import Text

from datetime import datetime

from app.db.database import Base


class AuditLog(Base):
    """
    Append-only record of who did what, when, scoped to an
    organization. This is intentionally a plain insert-only table -
    nothing in the API ever updates or deletes a row here, since an
    editable audit log isn't one.
    """

    __tablename__ = "audit_logs"

    id = Column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4())
    )

    organization_id = Column(
        String(36),
        ForeignKey("organizations.id"),
        nullable=False
    )

    actor_user_id = Column(
        String(36),
        ForeignKey("users.id"),
        nullable=True
    )

    actor_email = Column(String, nullable=True)

    # e.g. "user.register", "source.create", "scanner.scan",
    # "governance.certify", "glossary.create"
    action = Column(String, nullable=False)

    resource_type = Column(String, nullable=True)

    resource_id = Column(String, nullable=True)

    # Free-text/JSON-as-text detail, e.g. what changed. Kept as plain
    # Text rather than a JSON column since this never needs to be
    # queried on, only displayed.
    details = Column(Text, nullable=True)

    created_at = Column(
        DateTime,
        default=datetime.utcnow,
        nullable=False
    )
