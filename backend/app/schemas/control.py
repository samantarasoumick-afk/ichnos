from pydantic import BaseModel

from typing import Optional
from uuid import UUID

from datetime import datetime


class ControlCreate(BaseModel):

    name: str
    description: Optional[str] = None
    control_type: str = "PREVENTIVE"
    owner_user_id: Optional[UUID] = None


class ControlUpdate(BaseModel):

    name: Optional[str] = None
    description: Optional[str] = None
    control_type: Optional[str] = None
    status: Optional[str] = None
    owner_user_id: Optional[UUID] = None
    # Set true to stamp last_tested_at with now() - a status change on
    # its own doesn't imply a test just happened (e.g. correcting a
    # typo in the name shouldn't look like a fresh test).
    mark_tested_now: Optional[bool] = None


class ControlResponse(BaseModel):

    id: UUID
    name: str
    description: Optional[str] = None
    control_type: str
    status: str
    owner_user_id: Optional[UUID] = None
    owner_email: Optional[str] = None
    last_tested_at: Optional[datetime] = None
    risk_count: int = 0
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True
