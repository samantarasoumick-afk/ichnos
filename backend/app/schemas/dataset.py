from pydantic import BaseModel
from typing import Optional
from uuid import UUID
from datetime import datetime


class DatasetResponse(BaseModel):

    id: UUID
    source_id: Optional[UUID] = None
    source_name: Optional[str] = None
    source_type: Optional[str] = None
    name: str
    schema_name: str

    description: Optional[str] = None

    domain: Optional[str] = None
    steward: Optional[str] = None
    tags: Optional[str] = None
    certification: Optional[str] = None

    owner: Optional[str] = None

    system_role: Optional[str] = None
    data_category: Optional[str] = None

    sensitivity_score: Optional[str] = None
    governance_status: Optional[str] = None
    governance_score: Optional[int] = 0

    total_columns: Optional[int] = 0
    pii_columns: Optional[int] = 0
    risk_score: Optional[int] = 0
    
    freshness_status: Optional[str] = None
    trust_score: Optional[int] = 0
    
    quality_score: Optional[int] = 0
    operational_status: Optional[str] = None

    contract_status: Optional[str] = None
    pending_certification_request_id: Optional[UUID] = None

    # Privacy/governance policy fields - already computed on the model
    # (see app/models/dataset.py) but not previously surfaced over the
    # API; additive, so no existing consumer is affected.
    purpose: Optional[str] = None
    consent_status: Optional[str] = None
    retention_period_days: Optional[int] = None
    retention_status: Optional[str] = None
    privacy_score: Optional[int] = 0

    view_count: Optional[int] = 0
    distinct_viewer_count: Optional[int] = 0
    last_viewed_at: Optional[datetime] = None

    ai_summary: Optional[str] = None

    class Config:
        from_attributes = True
