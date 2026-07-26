import uuid

from datetime import datetime

from sqlalchemy import Boolean
from sqlalchemy import Column
from sqlalchemy import DateTime
from sqlalchemy import ForeignKey
from sqlalchemy import Integer
from sqlalchemy import String
from sqlalchemy import Text

from app.db.database import Base


class QueryLog(Base):
    """
    One row per question asked on the Ask page or query typed into the
    global search bar - the raw signal behind the admin "unanswered
    questions" report. Deliberately its own table rather than reused
    AuditLog rows, same reasoning as DatasetView: this is a usage/gap
    signal (what are people trying to find, and are they finding it),
    not a compliance trail of who-changed-what.

    `matched` is a coarse, cheap-to-compute confidence signal - for
    search it's just "did this return any results," and for Ask it's
    "did this hit a specific intent/semantic match, or fall through to
    one of the assistant's few fixed give-up messages" (see
    query_log_service.classify_ask_answer). It's not a claim that a
    "matched" answer was actually correct or helpful, only that the
    system found *something* to say beyond "I don't know" - the point
    is to surface the gaps, not to grade every answer.
    """

    __tablename__ = "query_logs"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=False)

    actor_user_id = Column(String(36), ForeignKey("users.id"), nullable=True)
    actor_email = Column(String, nullable=True)

    # "ask" | "search"
    source = Column(String, nullable=False)

    query_text = Column(Text, nullable=False)
    matched = Column(Boolean, nullable=False)
    result_count = Column(Integer, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
