import uuid

from datetime import datetime

from sqlalchemy import Column
from sqlalchemy import DateTime
from sqlalchemy import ForeignKey
from sqlalchemy import String

from app.db.database import Base


class MagicLoginToken(Base):
    """
    A single-use, short-lived passwordless login token. Only the
    sha256 hash of the raw token is ever stored - the raw token exists
    only in the emailed link and the verify request - so a database
    leak alone can't be used to log in as anyone, the same principle
    already applied to password_hash and encrypted connection_config.
    """

    __tablename__ = "magic_login_tokens"

    id = Column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4())
    )

    user_id = Column(
        String(36),
        ForeignKey("users.id"),
        nullable=False
    )

    token_hash = Column(
        String,
        nullable=False,
        unique=True
    )

    expires_at = Column(DateTime, nullable=False)

    used_at = Column(DateTime, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
