import uuid

from datetime import datetime

from sqlalchemy import Column
from sqlalchemy import DateTime
from sqlalchemy import ForeignKey
from sqlalchemy import Integer
from sqlalchemy import JSON
from sqlalchemy import String

from sqlalchemy.orm import relationship

from app.db.database import Base


class DataContract(Base):
    """
    An opt-in, steward-authored agreement about what a dataset's shape
    and quality must look like - separate from what discovery/scanning
    *observes* it to currently look like. A dataset can have several
    contract rows over time (DRAFT -> ACTIVE -> DEPRECATED, or
    superseded by a new version); only one should be ACTIVE for a
    given dataset at a time, enforced in the API layer rather than a
    DB constraint (consistent with how other business rules in this
    app - e.g. "can't remove the last active admin" - are enforced).

    schema_expectations shape:
        {"columns": [
            {"name": "id", "data_type": "integer", "nullable": false, "required": true},
            ...
        ]}

    quality_thresholds and freshness_sla_hours are captured now (so a
    contract's shape doesn't need another migration later) but not yet
    enforced - that's Phase 2 (DQ threshold enforcement against the
    DataQuality actuals already computed on every scan/upload).
    """

    __tablename__ = "data_contracts"

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

    version = Column(Integer, nullable=False, default=1)

    # DRAFT / ACTIVE / DEPRECATED
    status = Column(String, nullable=False, default="DRAFT")

    owner = Column(String, nullable=True)

    schema_expectations = Column(JSON, nullable=False, default=dict)

    # Reserved for Phase 2 (DQ threshold enforcement) - not yet
    # evaluated against anything.
    quality_thresholds = Column(JSON, nullable=True)

    freshness_sla_hours = Column(Integer, nullable=True)

    # Populated by data_contract_service.evaluate_contract() every
    # time this contract is ACTIVE and its dataset is scanned/
    # uploaded/re-evaluated - this is what Dataset.contract_status
    # reads, rather than recomputing on every request.
    last_evaluated_at = Column(DateTime, nullable=True)

    # COMPLIANT / BREACHED - None until the first evaluation runs.
    last_status = Column(String, nullable=True)

    last_breach_details = Column(String, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)

    updated_at = Column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow
    )

    dataset = relationship("Dataset", back_populates="contracts")
