from sqlalchemy import Column
from sqlalchemy import String
from sqlalchemy import Boolean
from sqlalchemy import Float
from sqlalchemy import ForeignKey

from sqlalchemy.orm import relationship

import uuid

from app.db.database import Base


class DatasetColumn(Base):

    __tablename__ = "columns"

    id = Column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4())
    )

    dataset_id = Column(
        String(36),
        ForeignKey("datasets.id")
    )

    name = Column(String)

    data_type = Column(String)

    nullable = Column(Boolean)

    classification = Column(String)

    sensitivity_score = Column(String)

    confidence = Column(Float)

    detection_reason = Column(String)

    recommendation = Column(String)

    # DPDP/GDPR-relevant grouping, e.g. "contact", "financial",
    # "health", "biometric", "government_id", "sensitive_personal".
    dpdp_category = Column(String, nullable=True)

    # Whether this column represents personal data DPDP/GDPR would
    # treat as requiring a documented lawful basis / consent to
    # process. Auto-set by the privacy engine, editable by a steward.
    consent_required = Column(Boolean, default=False)

    # "AUTO" (privacy engine set it, safe to overwrite on rescan) or
    # "MANUAL" (a steward edited it - rescans must not clobber this).
    classification_source = Column(String, default="AUTO")

    # Steward-authored business context for this specific column -
    # never auto-set or auto-overwritten, unlike everything else on
    # this model. Distinct from Dataset.description (which is
    # AI-generated) - this is a manual annotation only a person adds.
    description = Column(String, nullable=True)

    # A small JSON-encoded array of example values for this column,
    # refreshed on every scan/upload regardless of
    # classification_source - purely descriptive ("what does this
    # data look like"), not a classification judgment, so a steward's
    # MANUAL override of classification doesn't freeze this too.
    sample_values = Column(String, nullable=True)

    dataset = relationship(
        "Dataset",
        back_populates="columns"
    )
