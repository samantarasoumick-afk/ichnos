import uuid

from datetime import datetime

from sqlalchemy import Column
from sqlalchemy import DateTime
from sqlalchemy import ForeignKey
from sqlalchemy import String
from sqlalchemy import Text
from sqlalchemy import UniqueConstraint

from app.db.database import Base


class Risk(Base):
    """
    A risk register entry - "unmasked PII in the downstream reporting
    layer," "no failover for the primary Postgres source." Likelihood
    and impact are the inputs a person actually assesses; the
    inherent/residual score and level are derived from those (plus
    linked Controls) at read time rather than stored, so they can
    never drift out of sync with what's actually recorded - same
    philosophy as the org-level maturity score.
    """

    __tablename__ = "risks"

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

    title = Column(String, nullable=False)

    description = Column(Text, nullable=True)

    # PRIVACY / SECURITY / OPERATIONAL / COMPLIANCE / DATA_QUALITY / OTHER
    category = Column(String, nullable=False, default="OTHER")

    # LOW / MEDIUM / HIGH - the two inputs to the inherent risk score.
    likelihood = Column(String, nullable=False, default="MEDIUM")
    impact = Column(String, nullable=False, default="MEDIUM")

    # OPEN / MITIGATED / ACCEPTED / CLOSED
    status = Column(String, nullable=False, default="OPEN")

    owner_user_id = Column(
        String(36),
        ForeignKey("users.id"),
        nullable=True
    )

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


class RiskDatasetLink(Base):

    __tablename__ = "risk_dataset_links"

    __table_args__ = (
        UniqueConstraint(
            "risk_id", "dataset_id",
            name="uq_risk_dataset_link"
        ),
    )

    id = Column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4())
    )

    risk_id = Column(
        String(36),
        ForeignKey("risks.id"),
        nullable=False
    )

    dataset_id = Column(
        String(36),
        ForeignKey("datasets.id"),
        nullable=False
    )

    created_at = Column(DateTime, default=datetime.utcnow)


class RiskProcessLink(Base):

    __tablename__ = "risk_process_links"

    __table_args__ = (
        UniqueConstraint(
            "risk_id", "process_id",
            name="uq_risk_process_link"
        ),
    )

    id = Column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4())
    )

    risk_id = Column(
        String(36),
        ForeignKey("risks.id"),
        nullable=False
    )

    process_id = Column(
        String(36),
        ForeignKey("business_processes.id"),
        nullable=False
    )

    created_at = Column(DateTime, default=datetime.utcnow)


class RiskControlLink(Base):
    """
    Many-to-many: one control (e.g. "Quarterly access review") can
    mitigate several risks, and one risk can have several controls
    covering different angles of it.
    """

    __tablename__ = "risk_control_links"

    __table_args__ = (
        UniqueConstraint(
            "risk_id", "control_id",
            name="uq_risk_control_link"
        ),
    )

    id = Column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4())
    )

    risk_id = Column(
        String(36),
        ForeignKey("risks.id"),
        nullable=False
    )

    control_id = Column(
        String(36),
        ForeignKey("controls.id"),
        nullable=False
    )

    created_at = Column(DateTime, default=datetime.utcnow)
