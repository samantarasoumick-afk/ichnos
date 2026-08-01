from sqlalchemy import Column
from sqlalchemy import String
from sqlalchemy import ForeignKey
from sqlalchemy import DateTime
from sqlalchemy import Integer

from sqlalchemy.orm import relationship

from datetime import datetime

import uuid

from app.db.database import Base


class Dataset(Base):

    __tablename__ = "datasets"

    id = Column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4())
    )

    name = Column(String)

    schema_name = Column(String)

    description = Column(String)

    ai_summary = Column(String)

    domain = Column(String)

    steward = Column(String)

    tags = Column(String)

    certification = Column(String)

    owner = Column(String)

    last_scanned_at = Column(
        DateTime,
        default=datetime.utcnow
    )

    # When this dataset was first discovered - distinct from
    # last_scanned_at (which updates on every rescan). Used as the
    # reference point for retention-policy age calculations.
    created_at = Column(
        DateTime,
        default=datetime.utcnow
    )

    source_id = Column(
        String(36),
        ForeignKey("data_sources.id")
    )

    organization_id = Column(
        String(36),
        ForeignKey("organizations.id"),
        nullable=False
    )

    # DPDP-style retention/purpose-limitation metadata. Nullable
    # because it's typically filled in by a steward after discovery,
    # not known automatically at scan time.
    retention_period_days = Column(Integer, nullable=True)

    retention_notes = Column(String, nullable=True)

    # Why this data is processed - DPDP/GDPR purpose-limitation.
    # Nullable/free-text because it's filled in by a steward, not
    # inferred automatically.
    purpose = Column(String, nullable=True)

    # NOT_ASSESSED (default) / CONSENT_OBTAINED / CONSENT_NOT_REQUIRED.
    # A steward call, not something the scanner can determine on its
    # own - a column merely *containing* personal data doesn't tell
    # you whether consent was actually collected for it.
    consent_status = Column(String, default="NOT_ASSESSED")

    # NULL / SYSTEM_OF_RECORD / SYSTEM_OF_REFERENCE. A simple,
    # steward-set tag - never inferred - marking whether this dataset
    # is the authoritative source for its entity or a derived/
    # downstream copy of one.
    system_role = Column(String, nullable=True)

    # NULL / MASTER / REFERENCE / TRANSACTIONAL / ANALYTICAL.
    # Auto-classified once at creation time (see
    # app/utils/data_classification.py), overridable afterward by a
    # steward via the standard governance-update endpoint - same
    # "set once, editable later" precedent as owner/steward/domain.
    data_category = Column(String, nullable=True)

    # One-directional on purpose - nothing currently needs
    # DataSource.datasets as an ORM relationship (existing code queries
    # Dataset filtered by source_id directly wherever it needs "every
    # dataset under this source" - see ecosystem_service.py), so this
    # only adds the direction actually needed: a dataset page showing
    # which source it came from.
    source = relationship(
        "DataSource"
    )

    columns = relationship(
        "DatasetColumn",
        back_populates="dataset"
    )

    contracts = relationship(
        "DataContract",
        back_populates="dataset"
    )

    views = relationship(
        "DatasetView",
        back_populates="dataset"
    )

    certification_requests = relationship(
        "CertificationRequest",
        back_populates="dataset"
    )

    @property
    def sensitivity_score(self):

        if not self.columns:

            return "LOW"

        pii_count = 0

        sensitive_count = 0

        for column in self.columns:

            classification = (
                column.classification or ""
            ).upper()

            if classification == "PII":

                pii_count += 1

            # FINANCIAL (card numbers, bank accounts, IFSC codes, ...)
            # carries real risk even though the privacy engine tracks
            # it as a distinct classification from SENSITIVE - a
            # dataset made up entirely of financial identifiers must
            # not read as LOW sensitivity just because none of its
            # columns happen to be tagged PII or SENSITIVE.
            elif classification in ("SENSITIVE", "FINANCIAL"):

                sensitive_count += 1

        if pii_count >= 2:

            return "HIGH"

        if (
            pii_count >= 1 or
            sensitive_count >= 2
        ):

            return "MEDIUM"

        return "LOW"

    @property
    def source_name(self):
        """
        The connected system this dataset was scanned/uploaded from -
        previously not exposed anywhere on the dataset itself (only
        source_id, an opaque FK), so the dataset detail page had no way
        to show which source a dataset actually belongs to without a
        second lookup the frontend never made.
        """

        return self.source.name if self.source else None

    @property
    def source_type(self):

        return self.source.type if self.source else None

    @property
    def total_columns(self):

        return len(self.columns)

    @property
    def pii_columns(self):

        count = 0

        for column in self.columns:

            classification = (
                column.classification or ""
            ).upper()

            if classification == "PII":

                count += 1

        return count

    @property
    def governance_status(self):

        if self.sensitivity_score == "HIGH":

            if not self.steward:

                return "CRITICAL"

            if self.certification != "VERIFIED":

                return "REVIEW_REQUIRED"

        if self.sensitivity_score == "MEDIUM":

            if not self.description:

                return "REVIEW_REQUIRED"

        return "HEALTHY"

    @property
    def governance_score(self):

        score = 100

        if not self.owner:
            score -= 15

        if not self.steward:
            score -= 20

        if not self.domain:
            score -= 10

        if not self.description:
            score -= 10

        if not self.tags:
            score -= 10

        if self.certification != "VERIFIED":
            score -= 15

        if self.sensitivity_score == "HIGH":
            score -= 10

        if self.freshness_status == "STALE":
            score -= 10

        if self.quality_score < 70:
            score -= 10

        return max(score, 0)

    @property
    def risk_score(self):

        score = 0

        if self.sensitivity_score == "HIGH":

            score += 70

        elif self.sensitivity_score == "MEDIUM":

            score += 40

        else:

            score += 10

        if not self.description:

            score += 10

        if not self.steward:

            score += 10

        if self.certification != "VERIFIED":

            score += 10

        return min(score, 100)

    @property
    def freshness_status(self):

        if not self.last_scanned_at:
            return "STALE"

        age = datetime.utcnow() - self.last_scanned_at

        if age.days > 30:
            return "STALE"

        if age.days > 7:
            return "AGING"

        return "FRESH"

    @property
    def retention_status(self):
        """
        NOT_SET: no retention_period_days has been configured for
        this dataset - not a violation, just undecided.
        WITHIN_POLICY: still inside the configured window.
        OVERDUE: has been discovered for longer than its configured
        retention period. This only flags overdue data - it doesn't
        delete or restrict anything on its own.
        """

        if not self.retention_period_days:
            return "NOT_SET"

        reference = self.created_at or self.last_scanned_at

        if not reference:
            return "NOT_SET"

        age_days = (datetime.utcnow() - reference).days

        if age_days > self.retention_period_days:
            return "OVERDUE"

        return "WITHIN_POLICY"


    @property
    def trust_score(self):

        score = 100

        if self.governance_status == "CRITICAL":
            score -= 40

        elif self.governance_status == "REVIEW_REQUIRED":
            score -= 20

        if self.sensitivity_score == "HIGH":
            score -= 20

        if self.freshness_status == "STALE":
            score -= 20

        elif self.freshness_status == "AGING":
            score -= 10

        return max(score, 0)

    @property
    def quality_score(self):

        if not self.columns:
            return 0

        score = 100

        nullable_columns = 0

        unnamed_columns = 0

        for column in self.columns:

            if column.nullable:
                nullable_columns += 1

            if not column.name:
                unnamed_columns += 1

        nullable_ratio = (
            nullable_columns / len(self.columns)
        )

        if nullable_ratio > 0.5:
            score -= 25

        elif nullable_ratio > 0.3:
            score -= 10

        score -= unnamed_columns * 5

        return max(score, 0)  


    @property
    def privacy_score(self):
        """
        0-100. Only datasets that actually contain columns requiring
        consent (per the privacy engine's consent_required flag) are
        judged on consent/purpose/retention documentation - a dataset
        with no personal data isn't penalized for not having a
        consent status.
        """

        score = 100

        requires_consent = any(
            column.consent_required for column in self.columns
        )

        if requires_consent:

            if self.consent_status == "NOT_ASSESSED":
                score -= 30

            if not self.purpose:
                score -= 15

            if self.retention_status == "OVERDUE":
                score -= 25
            elif self.retention_status == "NOT_SET":
                score -= 10

            high_risk_categories = {
                "government_id", "biometric", "health", "sensitive_personal"
            }

            has_low_confidence_high_risk_column = any(
                column.dpdp_category in high_risk_categories
                and column.confidence is not None
                and column.confidence < 0.7
                for column in self.columns
            )

            if has_low_confidence_high_risk_column:
                score -= 10

        elif self.retention_status == "OVERDUE":
            score -= 25

        return max(score, 0)

    @property
    def operational_status(self):

        if self.quality_score < 50:
            return "UNSTABLE"

        if self.governance_status == "CRITICAL":
            return "AT_RISK"

        if self.freshness_status == "STALE":
            return "DEGRADED"

        return "HEALTHY"

    @property
    def active_contract(self):
        """
        At most one contract should be ACTIVE per dataset at a time
        (enforced in the API layer on activation) - this is the
        steward-facing "current agreement", if one exists.
        """

        for contract in self.contracts:
            if contract.status == "ACTIVE":
                return contract

        return None

    @property
    def contract_status(self):
        """
        NO_CONTRACT: no active contract has ever been set up for this
        dataset - not a violation, just undecided (same philosophy as
        retention_status's NOT_SET).
        PENDING_EVALUATION: a contract is active but hasn't been
        checked against the dataset's current state yet (e.g. just
        activated, no scan/upload has run since).
        COMPLIANT / BREACHED: the result of the most recent evaluation
        (see data_contract_service.evaluate_contract), which runs
        automatically after every scan and file upload.
        """

        contract = self.active_contract

        if contract is None:
            return "NO_CONTRACT"

        if contract.last_status is None:
            return "PENDING_EVALUATION"

        return contract.last_status

    @property
    def view_count(self):
        """
        Deduplicated view count (see DatasetView / record_view's
        dedup window) - a raw pageload count would just measure who
        refreshes the most, not genuine usage.
        """

        return len(self.views)

    @property
    def distinct_viewer_count(self):
        """
        How many different people have looked at this dataset - the
        actual "peer validation" signal. Ten views from one person is
        weaker evidence of trustworthiness than one view each from
        ten people.
        """

        return len({view.user_id for view in self.views if view.user_id})

    @property
    def last_viewed_at(self):

        if not self.views:
            return None

        return max(view.viewed_at for view in self.views)

    @property
    def pending_certification_request_id(self):
        """
        The id of this dataset's open certification request, if any -
        used by the frontend to show "pending review" instead of a
        "Request Certification" button, and to route directly to the
        request for an admin to act on. At most one PENDING request
        should exist per dataset at a time (enforced when a new
        request is created).
        """

        for request in self.certification_requests:
            if request.status == "PENDING":
                return request.id

        return None
