import uuid

from datetime import datetime

from sqlalchemy import Column
from sqlalchemy import DateTime
from sqlalchemy import ForeignKey
from sqlalchemy import String

from sqlalchemy.orm import relationship

from app.db.database import Base


class GovernanceThread(Base):
    """
    A discussion thread between governance users (analysts, stewards,
    admins) - either a QUESTION ("what does this column mean?") or a
    PROPOSAL ("should we deprecate this table?"). Threads can be
    scoped to a dataset or left global (dataset_id nullable), which is
    why - unlike most child tables in this codebase - this one carries
    organization_id directly rather than being scoped purely via a
    join to Dataset: a global thread has no dataset to join through.
    """

    __tablename__ = "governance_threads"

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

    dataset_id = Column(
        String(36),
        ForeignKey("datasets.id"),
        nullable=True
    )

    # QUESTION / PROPOSAL / ISSUE
    thread_type = Column(String, nullable=False, default="QUESTION")

    title = Column(String, nullable=False)

    body = Column(String, nullable=True)

    # OPEN / RESOLVED
    status = Column(String, nullable=False, default="OPEN")

    created_by = Column(
        String(36),
        ForeignKey("users.id"),
        nullable=False
    )

    created_at = Column(DateTime, default=datetime.utcnow)

    resolved_by = Column(
        String(36),
        ForeignKey("users.id"),
        nullable=True
    )

    resolved_at = Column(DateTime, nullable=True)

    resolution_note = Column(String, nullable=True)

    # Who an ISSUE thread is raised for - the stakeholder who needs to
    # follow through on it. Not DB-constrained to thread_type=ISSUE,
    # but that's the only case the UI currently exposes it for.
    raised_for_user_id = Column(
        String(36),
        ForeignKey("users.id"),
        nullable=True
    )

    dataset = relationship("Dataset")

    author = relationship("User", foreign_keys=[created_by])

    resolver = relationship("User", foreign_keys=[resolved_by])

    raised_for = relationship("User", foreign_keys=[raised_for_user_id])

    replies = relationship(
        "GovernanceThreadReply",
        back_populates="thread",
        order_by="GovernanceThreadReply.created_at",
        cascade="all, delete-orphan",
    )


class GovernanceThreadReply(Base):

    __tablename__ = "governance_thread_replies"

    id = Column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4())
    )

    thread_id = Column(
        String(36),
        ForeignKey("governance_threads.id"),
        nullable=False
    )

    body = Column(String, nullable=False)

    created_by = Column(
        String(36),
        ForeignKey("users.id"),
        nullable=False
    )

    created_at = Column(DateTime, default=datetime.utcnow)

    thread = relationship("GovernanceThread", back_populates="replies")

    author = relationship("User", foreign_keys=[created_by])
