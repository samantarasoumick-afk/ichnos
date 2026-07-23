from pydantic import BaseModel

from typing import Optional
from uuid import UUID

from datetime import datetime


class ContractColumnExpectation(BaseModel):

    name: str
    data_type: Optional[str] = None
    nullable: Optional[bool] = None
    required: bool = True


class SchemaExpectations(BaseModel):

    columns: list[ContractColumnExpectation] = []


class DataContractCreate(BaseModel):

    dataset_id: UUID
    owner: Optional[str] = None
    schema_expectations: SchemaExpectations
    quality_thresholds: Optional[dict] = None
    freshness_sla_hours: Optional[int] = None


class DataContractUpdate(BaseModel):
    """
    Only a DRAFT contract can be edited in place - once ACTIVE, a
    change means authoring a new version (POST a new contract), not
    silently rewriting the agreement everyone already signed off on.
    """

    owner: Optional[str] = None
    schema_expectations: Optional[SchemaExpectations] = None
    quality_thresholds: Optional[dict] = None
    freshness_sla_hours: Optional[int] = None


class DataContractResponse(BaseModel):

    id: UUID
    dataset_id: UUID
    version: int
    status: str
    owner: Optional[str] = None
    schema_expectations: dict
    quality_thresholds: Optional[dict] = None
    freshness_sla_hours: Optional[int] = None
    last_evaluated_at: Optional[datetime] = None
    last_status: Optional[str] = None
    last_breach_details: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True
