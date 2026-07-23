import uuid

from sqlalchemy import Boolean
from sqlalchemy import Column
from sqlalchemy import String
from sqlalchemy import ForeignKey

from app.db.database import Base
from app.db.encrypted_types import EncryptedJSON


class DataSource(Base):

    __tablename__ = "data_sources"

    id = Column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4())
    )

    name = Column(
        String,
        nullable=False
    )

    type = Column(
        String,
        nullable=False
    )

    connection_config = Column(EncryptedJSON)

    organization_id = Column(
        String(36),
        ForeignKey("organizations.id"),
        nullable=False
    )

    # True for sources created by the demo data seeder rather than a
    # real connection/upload - lets a "Clear Demo Data" action find
    # and remove exactly what it added, and nothing a user connected
    # themselves, even if they reused a name that collides.
    is_seed_data = Column(Boolean, nullable=False, default=False)
