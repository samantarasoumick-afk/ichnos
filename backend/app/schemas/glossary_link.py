from pydantic import BaseModel

from typing import Optional
from uuid import UUID

from datetime import datetime


class GlossaryTermLinkCreate(BaseModel):

    term_id: UUID
    dataset_id: UUID

    # Omitted or null = the term applies to the whole dataset.
    column_id: Optional[UUID] = None


class GlossaryTermLinkResponse(BaseModel):

    id: UUID
    term_id: UUID
    term: str
    definition: str
    dataset_id: UUID
    column_id: Optional[UUID] = None
    column_name: Optional[str] = None
    created_at: Optional[datetime] = None
