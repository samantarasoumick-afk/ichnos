from pydantic import BaseModel

from typing import List, Optional
from uuid import UUID

from datetime import datetime


class RiskCreate(BaseModel):

    title: str
    description: Optional[str] = None
    category: str = "OTHER"
    likelihood: str = "MEDIUM"
    impact: str = "MEDIUM"
    owner_user_id: Optional[UUID] = None


class RiskUpdate(BaseModel):

    title: Optional[str] = None
    description: Optional[str] = None
    category: Optional[str] = None
    likelihood: Optional[str] = None
    impact: Optional[str] = None
    status: Optional[str] = None
    owner_user_id: Optional[UUID] = None


class RiskResponse(BaseModel):

    id: UUID
    title: str
    description: Optional[str] = None
    category: str
    likelihood: str
    impact: str
    status: str
    owner_user_id: Optional[UUID] = None
    owner_email: Optional[str] = None
    created_by: UUID
    created_by_email: Optional[str] = None

    # Derived, never stored - see app/services/risk_scoring.py.
    inherent_score: int
    inherent_level: str
    residual_score: int
    residual_level: str
    effective_control_count: int = 0

    dataset_count: int = 0
    process_count: int = 0
    control_count: int = 0

    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class RiskDatasetLinkCreate(BaseModel):

    dataset_id: UUID


class RiskProcessLinkCreate(BaseModel):

    process_id: UUID


class RiskControlLinkCreate(BaseModel):

    control_id: UUID


class RiskLinkedDataset(BaseModel):

    id: UUID
    name: str
    schema_name: str


class RiskLinkedProcess(BaseModel):

    id: UUID
    name: str


class RiskLinkedControl(BaseModel):

    id: UUID
    name: str
    status: str


class RiskDetailResponse(RiskResponse):

    linked_datasets: List[RiskLinkedDataset] = []
    linked_processes: List[RiskLinkedProcess] = []
    linked_controls: List[RiskLinkedControl] = []
