import uuid

from sqlalchemy import Column
from sqlalchemy import DateTime
from sqlalchemy import String

from datetime import datetime

from sqlalchemy.orm import relationship

from app.db.database import Base


class Organization(Base):

    __tablename__ = "organizations"

    id = Column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4())
    )

    name = Column(
        String,
        nullable=False
    )

    slug = Column(
        String,
        unique=True,
        nullable=False
    )

    created_at = Column(
        DateTime,
        default=datetime.utcnow
    )

    users = relationship(
        "User",
        back_populates="organization"
    )
