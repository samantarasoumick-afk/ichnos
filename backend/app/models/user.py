import uuid

from datetime import datetime

from sqlalchemy import Boolean
from sqlalchemy import Column
from sqlalchemy import DateTime
from sqlalchemy import ForeignKey
from sqlalchemy import String

from sqlalchemy.orm import relationship

from app.db.database import Base


class User(Base):

    __tablename__ = "users"

    id = Column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4())
    )

    email = Column(
        String,
        unique=True,
        nullable=False
    )

    # Nullable because an account created via "Sign in with GitHub"
    # (or any future OAuth provider) never sets one - there's no
    # password to hash. login_user() in app/api/auth.py explicitly
    # rejects a password-login attempt when this is None rather than
    # passing None into verify_password().
    password_hash = Column(
        String,
        nullable=True
    )

    # How this account can authenticate. "password" (the default)
    # covers both password login and magic-link, since a magic link
    # is just an alternate proof of owning a password-based account's
    # inbox - it doesn't get its own value here. "github" means the
    # account has no password and signs in only via GitHub OAuth
    # (github_id below).
    auth_provider = Column(
        String,
        default="password",
        nullable=False
    )

    # GitHub's own numeric user id (as a string, matching every other
    # id in this codebase), set the first time this account signs in
    # with "Sign in with GitHub" - whether that's how the account was
    # created, or a password/magic-link account linking GitHub later.
    # Nullable since most users will never set it; unique since two
    # DataFe accounts can't share one GitHub identity.
    github_id = Column(
        String,
        unique=True,
        nullable=True
    )

    role = Column(
        String,
        default="viewer"
    )

    # Deactivated members keep their audit-log history (actor_user_id
    # references stay valid) but can no longer authenticate. Preferred
    # over hard-deleting a user row for that reason.
    is_active = Column(
        Boolean,
        default=True,
        nullable=False
    )

    created_at = Column(
        DateTime,
        default=datetime.utcnow
    )

    organization_id = Column(
        String(36),
        ForeignKey("organizations.id"),
        nullable=False
    )

    organization = relationship(
        "Organization",
        back_populates="users"
    )
