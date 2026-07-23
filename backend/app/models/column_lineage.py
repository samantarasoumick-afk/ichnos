from sqlalchemy import Column
from sqlalchemy import ForeignKey
from sqlalchemy import String
from sqlalchemy import Text

from app.db.database import Base

import uuid


class ColumnLineage(Base):
    """
    Column-to-column lineage - a finer-grained sibling of
    DatasetLineage. Two datasets can be linked at the table level
    (DatasetLineage: "fct_customer_orders depends on stg_orders") while
    only some of their columns actually flow into each other, and a
    column can be renamed or transformed along the way (e.g.
    "card_number" upstream becoming "masked_card_last4" downstream) -
    information a table-level edge alone can't express.

    Deliberately its own table rather than a JSON blob on
    DatasetLineage: a downstream dataset's column can trace back to
    columns in more than one upstream dataset (a join), and keeping
    rows separate makes "what upstream columns feed this one column"
    a plain filtered query instead of a JSON-parsing exercise.
    """

    __tablename__ = "column_lineage"

    id = Column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4())
    )

    upstream_dataset_id = Column(
        String(36),
        ForeignKey("datasets.id"),
        nullable=False
    )

    upstream_column_name = Column(String, nullable=False)

    downstream_dataset_id = Column(
        String(36),
        ForeignKey("datasets.id"),
        nullable=False
    )

    downstream_column_name = Column(String, nullable=False)

    transformation_type = Column(String, nullable=True)

    transformation_description = Column(Text, nullable=True)

    # AUTO / MANUAL - mirrors DatasetLineage.documentation_source.
    documentation_source = Column(String, nullable=False, default="AUTO")
