from app.db.database import engine
from app.db.database import Base

from app.models.user import User
from app.models.source import DataSource
from app.models.dataset import Dataset
from app.models.column import DatasetColumn
from app.models.lineage import DatasetLineage
from app.models.data_quality import DataQuality
from app.models.governance import BusinessGlossaryTerm


Base.metadata.create_all(bind=engine)

print("Database tables created.")
