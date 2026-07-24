"""
Shared pytest setup: env vars needed by app.db.database / app.auth.*
must exist before any test module does `from app.main import app`,
and the schema needs to exist exactly once for the whole test
session against one shared SQLite file. Doing this per-test-file
instead (as each file used to) raced two test modules against the
same underlying SQLAlchemy engine (env vars are process-wide and
`os.environ.setdefault` only lets the first-imported module's values
win) and one file deleting "its" DB file out from under the shared
connection pool mid-session caused an intermittent
"attempt to write a readonly database" error.
"""

import os
import tempfile

from cryptography.fernet import Fernet

_DB_PATH = os.path.join(tempfile.gettempdir(), "metadata_platform_pytest.db")

os.environ.setdefault("DATABASE_URL", f"sqlite:///{_DB_PATH}")
os.environ.setdefault("SECRET_KEY", "test-secret-not-for-prod")
os.environ.setdefault("ENCRYPTION_KEY", Fernet.generate_key().decode())
os.environ.setdefault("CORS_ALLOWED_ORIGINS", "http://localhost:3000")
os.environ.setdefault("AUTO_CREATE_SCHEMA", "false")
os.environ.setdefault("DEMO_SEED", "false")
# The general API rate limiter is IP-keyed and in-memory; the whole
# suite runs from a single TestClient "IP" and easily exceeds any
# reasonable per-minute limit well before it exceeds anything a real
# user would hit. Off by default in tests; test_rate_limiting.py
# turns it on for its own module only.
os.environ.setdefault("RATE_LIMIT_ENABLED", "false")

if os.path.exists(_DB_PATH):
    os.remove(_DB_PATH)

from app.db.database import Base  # noqa: E402
from app.db.database import engine  # noqa: E402

# Base.metadata only knows about tables whose model class has been
# imported somewhere (SQLAlchemy registers a table on class
# definition, not lazily) - importing app.main pulls in every model
# module as a side effect, same as alembic/env.py has to do
# explicitly. Without this, create_all() below silently creates zero
# tables against an empty metadata object.
import app.main  # noqa: E402,F401

Base.metadata.create_all(bind=engine)
