import uuid

from sqlalchemy import Boolean
from sqlalchemy import Column
from sqlalchemy import DateTime
from sqlalchemy import String
from sqlalchemy import Text
from sqlalchemy import ForeignKey
from sqlalchemy import UniqueConstraint

from datetime import datetime

from app.db.database import Base


class BusinessGlossaryTerm(Base):

    __tablename__ = "business_glossary_terms"

    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "term",
            name="uq_glossary_term_per_org"
        ),
    )

    id = Column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4())
    )

    term = Column(
        String,
        nullable=False
    )

    definition = Column(
        Text,
        nullable=False
    )

    domain = Column(String)

    owner = Column(String)

    organization_id = Column(
        String(36),
        ForeignKey("organizations.id"),
        nullable=False
    )

    status = Column(
        String,
        default="DRAFT"
    )

    created_at = Column(
        DateTime,
        default=datetime.utcnow
    )

    updated_at = Column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow
    )

    # True for terms created by the demo data seeder - lets "Clear
    # Demo Data" remove exactly what it added.
    is_seed_data = Column(Boolean, nullable=False, default=False)
