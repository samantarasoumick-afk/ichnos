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
    # schema.table label for the linked dataset - added so the
    # frontend can render "public.customers" for a dataset-level link
    # instead of the literal word "dataset" (there was previously no
    # way to tell which dataset a link pointed at without a separate
    # lookup, since only dataset_id - not a human-readable name - came
    # back from this endpoint).
    dataset_schema_name: Optional[str] = None
    dataset_name: Optional[str] = None
    column_id: Optional[UUID] = None
    column_name: Optional[str] = None
    created_at: Optional[datetime] = None
