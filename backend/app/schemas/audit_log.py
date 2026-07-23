from pydantic import BaseModel
from typing import Optional
from uuid import UUID
from datetime import datetime


class AuditLogResponse(BaseModel):

    id: UUID
    actor_user_id: Optional[UUID] = None
    actor_email: Optional[str] = None
    action: str
    resource_type: Optional[str] = None
    resource_id: Optional[str] = None
    details: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True
