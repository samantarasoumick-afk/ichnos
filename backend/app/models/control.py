import uuid

from datetime import datetime

from sqlalchemy import Column
from sqlalchemy import DateTime
from sqlalchemy import ForeignKey
from sqlalchemy import String
from sqlalchemy import Text

from app.db.database import Base


class Control(Base):
    """
    A reusable mitigation - "Quarterly access review," "Column-level
    masking on export," "MFA required for admin role." Deliberately
    its own entity rather than a free-text field on Risk, since real
    GRC practice reuses the same control across many risks (one access
    review policy mitigates several different risks at once) and wants
    to track whether that control is actually working independently of
    any single risk it happens to cover.
    """

    __tablename__ = "controls"

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

    name = Column(String, nullable=False)

    description = Column(Text, nullable=True)

    # PREVENTIVE / DETECTIVE / CORRECTIVE
    control_type = Column(String, nullable=False, default="PREVENTIVE")

    # EFFECTIVE / INEFFECTIVE / NOT_TESTED
    status = Column(String, nullable=False, default="NOT_TESTED")

    owner_user_id = Column(
        String(36),
        ForeignKey("users.id"),
        nullable=True
    )

    last_tested_at = Column(DateTime, nullable=True)

    created_by = Column(
        String(36),
        ForeignKey("users.id"),
        nullable=False
    )

    created_at = Column(DateTime, default=datetime.utcnow)

    updated_at = Column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow
    )
