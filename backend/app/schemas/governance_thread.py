from pydantic import BaseModel

from typing import List
from typing import Optional
from uuid import UUID

from datetime import datetime


class GovernanceThreadCreate(BaseModel):

    dataset_id: Optional[UUID] = None
    thread_type: str = "QUESTION"
    title: str
    body: Optional[str] = None
    # The stakeholder this thread should be followed up with - mainly
    # meaningful for ISSUE threads, but not restricted to them.
    raised_for_user_id: Optional[UUID] = None


class GovernanceThreadReplyCreate(BaseModel):

    body: str


class GovernanceThreadResolve(BaseModel):

    resolution_note: Optional[str] = None


class GovernanceThreadReplyResponse(BaseModel):

    id: UUID
    thread_id: UUID
    body: str
    created_by: UUID
    created_by_email: Optional[str] = None
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class GovernanceThreadResponse(BaseModel):

    id: UUID
    dataset_id: Optional[UUID] = None
    dataset_label: Optional[str] = None
    thread_type: str
    title: str
    body: Optional[str] = None
    status: str
    created_by: UUID
    created_by_email: Optional[str] = None
    created_at: Optional[datetime] = None
    resolved_by: Optional[UUID] = None
    resolved_by_email: Optional[str] = None
    resolved_at: Optional[datetime] = None
    resolution_note: Optional[str] = None
    raised_for_user_id: Optional[UUID] = None
    raised_for_email: Optional[str] = None
    reply_count: int = 0

    class Config:
        from_attributes = True


class GovernanceThreadDetailResponse(GovernanceThreadResponse):

    replies: List[GovernanceThreadReplyResponse] = []
