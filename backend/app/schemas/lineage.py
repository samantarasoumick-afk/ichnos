from pydantic import BaseModel

from uuid import UUID

from typing import Optional


class LineageCreate(BaseModel):

    upstream_dataset_id: UUID

    downstream_dataset_id: UUID

    transformation_type: Optional[str] = None

    # Only meaningful for a manually-documented edge - discovery-
    # created edges never set these (there's no human writing them at
    # scan time).
    transformation_description: Optional[str] = None

    filter_logic: Optional[str] = None


class LineageUpdate(BaseModel):
    """
    Lets a steward add or correct documentation on an edge after the
    fact - e.g. discovery created a bare "FOREIGN_KEY" edge and
    someone wants to explain what the join/filter actually does.
    upstream/downstream dataset ids are intentionally not editable
    here - to reconnect different datasets, delete and recreate the
    edge rather than silently repointing an existing one.
    """

    transformation_type: Optional[str] = None

    transformation_description: Optional[str] = None

    filter_logic: Optional[str] = None


class LineageResponse(BaseModel):

    id: UUID

    upstream_dataset_id: UUID

    downstream_dataset_id: UUID

    transformation_type: Optional[str] = None

    transformation_description: Optional[str] = None

    filter_logic: Optional[str] = None

    documentation_source: str = "AUTO"

    class Config:

        from_attributes = True
