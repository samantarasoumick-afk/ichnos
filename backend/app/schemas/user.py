from datetime import datetime

from pydantic import BaseModel
from pydantic import EmailStr
from pydantic import Field
from typing import Optional
from uuid import UUID


class UserCreate(BaseModel):

    email: EmailStr

    password: str = Field(min_length=8)

    # Every signup creates a brand-new organization for now (no
    # invite flow yet). The first user of an organization is made
    # an admin in the register endpoint.
    organization_name: str = Field(min_length=1)


class UserLogin(BaseModel):

    email: EmailStr

    password: str


class MagicLinkRequest(BaseModel):

    email: EmailStr


class MagicLinkVerify(BaseModel):

    token: str


class GitHubOAuthCallback(BaseModel):

    code: str
    state: str


class TeamMemberInvite(BaseModel):

    email: EmailStr

    # An admin sets an initial password directly and shares it with
    # the new member out of band - there's no outbound email/SMTP
    # integration yet, so a "send an invite link" flow isn't possible.
    password: str = Field(min_length=8)

    role: str = Field(default="viewer")


class TeamMemberUpdate(BaseModel):

    role: Optional[str] = None
    is_active: Optional[bool] = None


class TeamMemberResponse(BaseModel):

    id: UUID
    email: str
    role: str
    is_active: bool
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True
