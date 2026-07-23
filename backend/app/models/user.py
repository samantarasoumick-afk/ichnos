import uuid

from datetime import datetime

from sqlalchemy import Boolean
from sqlalchemy import Column
from sqlalchemy import DateTime
from sqlalchemy import ForeignKey
from sqlalchemy import String

from sqlalchemy.orm import relationship

from app.db.database import Base


class User(Base):

    __tablename__ = "users"

    id = Column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4())
    )

    email = Column(
        String,
        unique=True,
        nullable=False
    )

    password_hash = Column(
        String,
        nullable=False
    )

    role = Column(
        String,
        default="viewer"
    )

    # Deactivated members keep their audit-log history (actor_user_id
    # references stay valid) but can no longer authenticate. Preferred
    # over hard-deleting a user row for that reason.
    is_active = Column(
        Boolean,
        default=True,
        nullable=False
    )

    created_at = Column(
        DateTime,
        default=datetime.utcnow
    )

    organization_id = Column(
        String(36),
        ForeignKey("organizations.id"),
        nullable=False
    )

    organization = relationship(
        "Organization",
        back_populates="users"
    )
