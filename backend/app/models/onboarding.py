import uuid

from datetime import datetime

from sqlalchemy import Column
from sqlalchemy import DateTime
from sqlalchemy import ForeignKey
from sqlalchemy import String
from sqlalchemy import UniqueConstraint

from app.db.database import Base


class OnboardingMilestoneEvent(Base):
    """
    One row per (user, milestone) the first time that user hits a
    given Ecosystem View onboarding milestone - the raw signal behind
    the "3 months down to 10 days" claim: instead of asserting it,
    the app can show exactly which real actions a new analyst has
    taken (viewed the map, explored a front/middle/back-office node,
    traced a report's provenance, used semantic search) and how many
    calendar days elapsed between the first and the last.

    Deliberately its own table rather than reused AuditLog rows, same
    reasoning as DatasetView: this is a usage/progress signal, not a
    compliance trail. The unique constraint makes recording a
    milestone naturally idempotent (hitting it again is a no-op, not
    a duplicate row) - the same "record the first time, ignore after"
    semantics DatasetView's dedup window approximates for views.
    """

    __tablename__ = "onboarding_milestone_events"

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

    user_id = Column(
        String(36),
        ForeignKey("users.id"),
        nullable=False
    )

    # See onboarding_service.MILESTONES for the fixed, ordered set of
    # valid keys - not a DB enum so a new milestone can be added
    # without a migration, matching the "no leading underscore" free-
    # text-key convention DatasetLineage.transformation_type also uses.
    milestone_key = Column(String, nullable=False)

    achieved_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint("user_id", "milestone_key", name="uq_onboarding_milestone_user_key"),
    )
