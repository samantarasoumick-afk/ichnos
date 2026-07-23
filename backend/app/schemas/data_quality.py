from pydantic import BaseModel
from typing import List, Optional
from uuid import UUID


class DataQualityResponse(BaseModel):

    id: UUID
    dataset_id: UUID

    completeness: Optional[float] = None
    uniqueness: Optional[float] = None
    validity: Optional[float] = None
    consistency: Optional[float] = None
    freshness: Optional[float] = None
    overall_score: Optional[float] = None

    class Config:
        from_attributes = True


class ContributingEdge(BaseModel):

    edge_id: str
    upstream_dataset_id: str
    upstream_effective_score: float
    documentation_completeness: int
    adjustment: float
    contribution: float


class EffectiveQualityResponse(BaseModel):

    dataset_id: str
    own_score: Optional[float] = None
    effective_score: Optional[float] = None
    contributing_edges: List[ContributingEdge] = []
