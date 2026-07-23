from pydantic import BaseModel

from typing import Optional
from uuid import UUID

from datetime import datetime


class BusinessProcessCreate(BaseModel):

    name: str
    description: Optional[str] = None
    owner: Optional[str] = None


class BusinessProcessUpdate(BaseModel):

    name: Optional[str] = None
    description: Optional[str] = None
    owner: Optional[str] = None


class BusinessProcessResponse(BaseModel):

    id: UUID
    name: str
    description: Optional[str] = None
    owner: Optional[str] = None
    dataset_count: int = 0
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class BusinessProcessLinkCreate(BaseModel):

    dataset_id: UUID


class BusinessProcessLinkResponse(BaseModel):

    id: UUID
    process_id: UUID
    process_name: str
    dataset_id: UUID
    created_at: Optional[datetime] = None


class BusinessProcessDatasetSummary(BaseModel):

    id: UUID
    name: str
    schema_name: str
