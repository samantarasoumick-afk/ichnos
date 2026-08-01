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
    activated_by_email: Optional[str] = None
    activated_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class ContractHistoryEntry(BaseModel):
    """
    One audit-log row for this dataset's contract activity (create/
    activate/deprecate/breach) - not a separate table, just the
    existing AuditLog rows app.services.data_contract_service and
    app.api.data_contracts already write on every one of those events,
    filtered down and reordered for display. actor_email is None for
    a "contract.breach" entry raised by an unattended rescan (no user
    was driving it) rather than someone's direct action.
    """

    action: str
    actor_email: Optional[str] = None
    details: Optional[str] = None
    created_at: datetime


class UpstreamContractBreach(BaseModel):
    """
    One upstream dataset (reachable via lineage) whose ACTIVE contract
    is currently BREACHED - surfaced to a downstream dataset so its
    consumers know a data-quality or schema problem is coming from
    somewhere further up the pipeline, not necessarily from this
    dataset itself.
    """

    dataset_id: UUID
    dataset_name: str
    schema_name: str
    contract_id: UUID
    contract_version: int
    breach_details: Optional[str] = None
