from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel


class QueryLogEntry(BaseModel):
    id: UUID
    source: str
    query_text: str
    matched: bool
    result_count: Optional[int] = None
    actor_email: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


class QueryGroup(BaseModel):
    query_text: str
    count: int
    sources: list[str]
    last_asked_at: datetime


class QueryLogReport(BaseModel):
    window_days: int
    total_queries: int
    unanswered_count: int
    unanswered_rate: float
    top_unanswered: list[QueryGroup]
    top_overall: list[QueryGroup]
