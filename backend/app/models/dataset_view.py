import uuid

from datetime import datetime

from sqlalchemy import Column
from sqlalchemy import DateTime
from sqlalchemy import ForeignKey
from sqlalchemy import String

from sqlalchemy.orm import relationship

from app.db.database import Base


class DatasetView(Base):
    """
    One row per (deduplicated) time a user opens a dataset's detail
    page - the raw signal behind Dataset.view_count /
    distinct_viewer_count / last_viewed_at. Deliberately its own
    table rather than reused AuditLog rows: AuditLog is a compliance
    trail (who changed what), and a flood of "dataset.view" events on
    every page load would drown out the governance-relevant actions
    it's meant to surface. This is a usage/popularity signal instead -
    peer validation ("other people actually use and trust this
    dataset"), not an audit record.
    """

    __tablename__ = "dataset_views"

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

    # Nullable in case a future non-user actor (an API key, a
    # scheduled digest job) ever needs to record a view without a
    # human user behind it - not used today, every view is recorded
    # against the requesting user.
    user_id = Column(
        String(36),
        ForeignKey("users.id"),
        nullable=True
    )

    viewed_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    dataset = relationship("Dataset", back_populates="views")
