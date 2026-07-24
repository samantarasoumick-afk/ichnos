import uuid

from datetime import datetime

from sqlalchemy import Boolean
from sqlalchemy import Column
from sqlalchemy import DateTime
from sqlalchemy import ForeignKey
from sqlalchemy import String
from sqlalchemy import Text
from sqlalchemy import UniqueConstraint

from app.db.database import Base


class BusinessProcess(Base):
    """
    The "process dimension" - a business-facing taxonomy like
    "Order-to-Cash" or "Customer Onboarding" that datasets get tagged
    with. Domain (on Dataset) answers "which team's data is this";
    process answers a different question - "which end-to-end business
    activity does this data support" - and a dataset can support more
    than one process (a customers table serves both Customer
    Onboarding and Order-to-Cash), which is why this is a many-to-many
    link (BusinessProcessLink below), the same shape as glossary
    linking.
    """

    __tablename__ = "business_processes"

    __table_args__ = (
        UniqueConstraint(
            "organization_id", "name",
            name="uq_business_process_name_per_org"
        ),
    )

    id = Column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4())
    )

    name = Column(String, nullable=False)

    description = Column(Text, nullable=True)

    # Free-text story of how the linked datasets actually interact -
    # e.g. "A Customer (Master) orders (Transactional) from a Store
    # (Master) in Mumbai (Reference)." Written by a steward, displayed
    # alongside the linked datasets grouped by data_category
    # (Master/Reference/Transactional/Analytical) on the process page.
    narrative = Column(Text, nullable=True)

    owner = Column(String, nullable=True)

    organization_id = Column(
        String(36),
        ForeignKey("organizations.id"),
        nullable=False
    )

    created_at = Column(DateTime, default=datetime.utcnow)

    updated_at = Column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow
    )

    # True for processes created by the demo data seeder - lets
    # "Clear Demo Data" remove exactly what it added.
    is_seed_data = Column(Boolean, nullable=False, default=False)


class BusinessProcessLink(Base):

    __tablename__ = "business_process_links"

    __table_args__ = (
        UniqueConstraint(
            "process_id", "dataset_id",
            name="uq_business_process_link_process_dataset"
        ),
    )

    id = Column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4())
    )

    process_id = Column(
        String(36),
        ForeignKey("business_processes.id"),
        nullable=False
    )

    dataset_id = Column(
        String(36),
        ForeignKey("datasets.id"),
        nullable=False
    )

    created_at = Column(DateTime, default=datetime.utcnow)
