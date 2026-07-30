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

    Enforcement happens in data_contract_service.evaluate_contract(),
    called automatically every time this dataset's columns are synced
    (a live source rescan or a file/dbt upload - see
    dataset_ingestion_service.sync_columns()) and once immediately on
    activation (app.api.data_contracts's /activate endpoint), so a
    freshly-activated contract doesn't sit at "not yet evaluated" until
    the next scan happens to run. It checks schema_expectations
    (missing required columns, type mismatches, unexpected
    nullability) and, if set, quality_thresholds.min_overall_score
    against the dataset's most recently profiled DataQuality score -
    both feed the same last_status/last_breach_details write.
    freshness_sla_hours is captured now (so a contract's shape doesn't
    need another migration later) but not yet enforced against
    anything.
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

    # Who actually turned enforcement on for this specific contract
    # version, and when - set once, in the /activate endpoint, the
    # moment status flips DRAFT -> ACTIVE. None for a contract that's
    # never been activated (still DRAFT) or that was created directly
    # active by a migration/seed path. This is "who enforced it" as a
    # persisted fact rather than something reconstructed from the
    # audit log (which also gets a contract.activate entry at the same
    # moment, for the org-wide activity trail).
    activated_by_email = Column(String, nullable=True)

    activated_at = Column(DateTime, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)

    updated_at = Column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow
    )

    dataset = relationship("Dataset", back_populates="contracts")
