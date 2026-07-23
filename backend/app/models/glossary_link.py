import uuid

from datetime import datetime

from sqlalchemy import Column
from sqlalchemy import DateTime
from sqlalchemy import ForeignKey
from sqlalchemy import String
from sqlalchemy import UniqueConstraint

from app.db.database import Base


class GlossaryTermLink(Base):
    """
    Connects a BusinessGlossaryTerm to the technical catalog - the
    thing that was missing entirely before this: a glossary term and
    a dataset/column used to only ever meet by coincidence, in the
    Ask Assistant's fuzzy semantic search. This is a real, explicit
    link a steward makes on purpose.

    column_id is nullable by design, giving two link granularities in
    one table rather than two: NULL means the term describes the
    dataset as a whole (e.g. "Customer" -> the customers table); a
    real column_id means the term defines that one column precisely
    (e.g. "Customer Lifetime Value" -> dim_customers.lifetime_value).
    dataset_id is always set even for a column-level link (not just
    derivable through the column) so "every term touching this
    dataset" is a single indexed filter, not a join through columns.
    """

    __tablename__ = "glossary_term_links"

    __table_args__ = (
        UniqueConstraint(
            "term_id", "dataset_id", "column_id",
            name="uq_glossary_link_term_dataset_column"
        ),
    )

    id = Column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4())
    )

    term_id = Column(
        String(36),
        ForeignKey("business_glossary_terms.id"),
        nullable=False
    )

    dataset_id = Column(
        String(36),
        ForeignKey("datasets.id"),
        nullable=False
    )

    # NULL = applies to the whole dataset. Set = applies to exactly
    # this one column.
    column_id = Column(
        String(36),
        ForeignKey("columns.id"),
        nullable=True
    )

    created_at = Column(DateTime, default=datetime.utcnow)
