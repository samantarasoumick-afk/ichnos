import uuid

from sqlalchemy import Column
from sqlalchemy import Float
from sqlalchemy import String
from sqlalchemy import ForeignKey

from app.db.database import Base


class DataQuality(Base):

    __tablename__ = "data_quality"

    id = Column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4())
    )

    dataset_id = Column(
        String(36),
        ForeignKey("datasets.id"),
        unique=True
    )

    completeness = Column(Float)

    uniqueness = Column(Float)

    validity = Column(Float)

    freshness = Column(Float)

    consistency = Column(Float)

    overall_score = Column(Float)