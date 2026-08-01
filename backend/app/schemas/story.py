from pydantic import BaseModel

from typing import Optional
from uuid import UUID

from datetime import datetime


class StoryStepDatasetRef(BaseModel):
    schema_name: str
    table_name: str


class StoryStepCreate(BaseModel):

    title: str
    narrative: str
    path: str
    dataset: Optional[StoryStepDatasetRef] = None
    tab: Optional[str] = None
    query: Optional[dict[str, str]] = None


class StoryStepResponse(BaseModel):

    id: UUID
    order_index: int
    title: str
    narrative: str
    path: str
    dataset_schema_name: Optional[str] = None
    dataset_table_name: Optional[str] = None
    tab: Optional[str] = None
    query_params: Optional[dict[str, str]] = None

    class Config:
        from_attributes = True


class StoryCreate(BaseModel):

    title: str
    problem: Optional[str] = None
    solution_summary: Optional[str] = None
    # Ordered start-to-finish - order_index on each saved StoryStep is
    # derived from position in this list, not supplied by the client.
    steps: list[StoryStepCreate]


class StorySummary(BaseModel):
    """
    Listing shape - deliberately excludes `steps` (fetched separately
    via GET /api/stories/{id} only when someone actually starts
    playing the story), matching the way TourPickerModal already only
    needs title/problem/step-count to render a picker card for the two
    built-in scenarios.
    """

    id: UUID
    title: str
    problem: Optional[str] = None
    solution_summary: Optional[str] = None
    step_count: int
    created_by_email: Optional[str] = None
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class StoryResponse(BaseModel):

    id: UUID
    title: str
    problem: Optional[str] = None
    solution_summary: Optional[str] = None
    created_by_email: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    steps: list[StoryStepResponse]

    class Config:
        from_attributes = True
