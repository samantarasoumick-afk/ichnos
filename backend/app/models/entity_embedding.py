import uuid

from datetime import datetime

from sqlalchemy import Column
from sqlalchemy import DateTime
from sqlalchemy import ForeignKey
from sqlalchemy import Integer
from sqlalchemy import String
from sqlalchemy import Text
from sqlalchemy import UniqueConstraint

from app.db.database import Base


class EntityEmbedding(Base):
    """
    A cached dense-vector embedding for one entity (a dataset, glossary
    term, process, risk, control, or discussion thread - the same
    DocType set app/services/catalog_search_service.py's corpus
    covers), used by app/services/embedding_service.py to power
    semantic search/retrieval without re-calling the embeddings API on
    every request.

    One row per (entity_type, entity_id) - `text_hash` is a sha256 of
    the exact text that was embedded (the same text
    catalog_search_service's _*_document() builders produce), so a
    row is only reused when the underlying entity hasn't changed since
    it was last embedded; any edit changes the hash and the next
    search naturally re-embeds it. `model` is stored alongside the
    vector rather than assumed, so switching VOYAGE_MODEL invalidates
    every cached vector automatically instead of silently comparing
    vectors from two incompatible embedding spaces.

    Deliberately not a strict foreign key to any one entity table -
    entity_type/entity_id is a loose reference across six different
    tables, the same "polymorphic by discriminator" shape
    GlossaryTermLink and the audit log already use elsewhere in this
    schema. A row can outlive its entity (e.g. a risk gets deleted) -
    that's a harmless orphan, never a correctness problem, since
    nothing will ever look it up again once the entity itself is gone
    from build_corpus()'s query results. clear_demo_data() cleans
    these up proactively anyway, for the high-churn seed/clear cycle.
    """

    __tablename__ = "entity_embeddings"

    __table_args__ = (
        UniqueConstraint(
            "entity_type", "entity_id",
            name="uq_entity_embedding_entity"
        ),
    )

    id = Column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4())
    )

    organization_id = Column(
        String(36),
        ForeignKey("organizations.id"),
        nullable=False
    )

    # dataset / glossary_term / process / risk / control / discussion_thread
    entity_type = Column(String, nullable=False)

    entity_id = Column(String(36), nullable=False)

    text_hash = Column(String(64), nullable=False)

    model = Column(String, nullable=False)

    dimension = Column(Integer, nullable=False)

    # JSON-encoded list[float] rather than a native vector column/
    # pgvector extension - this app runs on both Postgres (production)
    # and SQLite (tests), and at the catalog scale documented in
    # catalog_search_service.py (a few thousand rows), loading these as
    # plain JSON and comparing with numpy at request time is well
    # within budget without adding a Postgres-only dependency.
    vector = Column(Text, nullable=False)

    created_at = Column(DateTime, default=datetime.utcnow)

    updated_at = Column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow
    )
