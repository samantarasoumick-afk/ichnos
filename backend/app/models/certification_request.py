import uuid

from datetime import datetime

from sqlalchemy import Column
from sqlalchemy import DateTime
from sqlalchemy import ForeignKey
from sqlalchemy import String

from sqlalchemy.orm import relationship

from app.db.database import Base


class CertificationRequest(Base):
    """
    The approval workflow behind a dataset reaching certification
    "VERIFIED": a steward (or admin) requests certification, and a
    *different* admin (segregation of duties, same idea as "can't
    remove the last active admin") approves or rejects it - rather
    than any admin/steward being able to self-declare a dataset
    trustworthy by flipping a dropdown. Direct edits to VERIFIED are
    blocked in app/api/governance.py; this is the only path there.
    """

    __tablename__ = "certification_requests"

    id = Column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4())
    )

    dataset_id = Column(
        String(36),
        ForeignKey("datasets.id"),
        nullable=False
    )

    requested_by = Column(
        String(36),
        ForeignKey("users.id"),
        nullable=False
    )

    request_note = Column(String, nullable=True)

    # PENDING / APPROVED / REJECTED
    status = Column(String, nullable=False, default="PENDING")

    reviewed_by = Column(
        String(36),
        ForeignKey("users.id"),
        nullable=True
    )

    review_note = Column(String, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)

    reviewed_at = Column(DateTime, nullable=True)

    dataset = relationship("Dataset", back_populates="certification_requests")

    requester = relationship("User", foreign_keys=[requested_by])

    reviewer = relationship("User", foreign_keys=[reviewed_by])
