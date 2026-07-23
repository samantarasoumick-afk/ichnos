from pydantic import BaseModel

from uuid import UUID

from typing import Optional


class ColumnLineageResponse(BaseModel):

    id: UUID

    upstream_dataset_id: UUID

    upstream_column_name: str

    downstream_dataset_id: UUID

    downstream_column_name: str

    transformation_type: Optional[str] = None

    transformation_description: Optional[str] = None

    documentation_source: str = "AUTO"

    class Config:

        from_attributes = True
