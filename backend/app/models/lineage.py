from sqlalchemy import Column
from sqlalchemy import ForeignKey
from sqlalchemy import String
from sqlalchemy import Text

from app.db.database import Base

import uuid


class DatasetLineage(Base):

    __tablename__ = "dataset_lineage"

    id = Column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4())
    )

    upstream_dataset_id = Column(
        String(36),
        ForeignKey("datasets.id")
    )

    downstream_dataset_id = Column(
        String(36),
        ForeignKey("datasets.id")
    )

    transformation_type = Column(
        String
    )

    # Free-text explanation of what the transformation actually does -
    # for sources where it can't be auto-discovered (a CSV upload
    # carries no FK/transform metadata at all) or where the mechanical
    # "FOREIGN_KEY" label from discovery doesn't capture the real
    # business logic (a join is not the same thing as knowing *why*).
    transformation_description = Column(Text, nullable=True)

    # Filter conditions applied between upstream and downstream (e.g.
    # "WHERE status = 'active'", "excludes soft-deleted rows") - kept
    # separate from transformation_description since filtering and
    # transforming are different questions a consumer asks.
    filter_logic = Column(Text, nullable=True)

    # AUTO: created by LineageDiscoveryService from real FK metadata.
    # MANUAL: a human documented this edge through the API/UI, because
    # automated discovery isn't available for this source (or missed
    # a relationship FK scanning can't see, like a transform in a
    # script outside the database entirely).
    documentation_source = Column(String, nullable=False, default="AUTO")