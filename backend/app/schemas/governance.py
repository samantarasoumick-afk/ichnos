from pydantic import BaseModel

from typing import Optional
from uuid import UUID

from datetime import datetime


class DatasetGovernanceUpdate(BaseModel):

    owner: Optional[str] = None
    steward: Optional[str] = None
    domain: Optional[str] = None
    tags: Optional[str] = None
    certification: Optional[str] = None
    purpose: Optional[str] = None
    consent_status: Optional[str] = None
    retention_period_days: Optional[int] = None
    retention_notes: Optional[str] = None
    system_role: Optional[str] = None
    data_category: Optional[str] = None


class DatasetCertificationUpdate(BaseModel):

    certification: str


class DatasetTagUpdate(BaseModel):

    tags: str


class GovernanceScorecard(BaseModel):

    id: UUID
    name: str
    schema_name: str
    owner: Optional[str] = None
    steward: Optional[str] = None
    domain: Optional[str] = None
    tags: Optional[str] = None
    certification: Optional[str] = None
    system_role: Optional[str] = None
    data_category: Optional[str] = None
    governance_status: str
    governance_score: int
    risk_score: int
    trust_score: int
    sensitivity_score: str
    quality_score: int
    freshness_status: str

    purpose: Optional[str] = None
    consent_status: Optional[str] = None
    retention_period_days: Optional[int] = None
    retention_notes: Optional[str] = None
    retention_status: str
    privacy_score: int

    contract_status: Optional[str] = None
    pending_certification_request_id: Optional[UUID] = None

    class Config:
        from_attributes = True


class CertificationRequestCreate(BaseModel):

    dataset_id: UUID
    request_note: Optional[str] = None


class CertificationRequestReview(BaseModel):

    review_note: Optional[str] = None


class CertificationRequestResponse(BaseModel):

    id: UUID
    dataset_id: UUID
    requested_by: UUID
    requested_by_email: Optional[str] = None
    request_note: Optional[str] = None
    status: str
    reviewed_by: Optional[UUID] = None
    reviewed_by_email: Optional[str] = None
    review_note: Optional[str] = None
    created_at: Optional[datetime] = None
    reviewed_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class BusinessGlossaryTermCreate(BaseModel):

    term: str
    definition: str
    domain: Optional[str] = None
    owner: Optional[str] = None
    status: Optional[str] = "DRAFT"


class BusinessGlossaryTermUpdate(BaseModel):

    term: Optional[str] = None
    definition: Optional[str] = None
    domain: Optional[str] = None
    owner: Optional[str] = None
    status: Optional[str] = None


class BusinessGlossaryTermResponse(BaseModel):

    id: UUID
    term: str
    definition: str
    domain: Optional[str] = None
    owner: Optional[str] = None
    status: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    is_seed_data: bool = False

    class Config:
        from_attributes = True
