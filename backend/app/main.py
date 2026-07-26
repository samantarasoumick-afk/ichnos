# Load backend/.env before anything else - every module below that
# reads os.getenv() (database URL, JWT secret, encryption key, CORS
# origins) does so at import time, so this has to run first or those
# reads see nothing even when .env exists and is filled in correctly.
from dotenv import load_dotenv
load_dotenv()

# Structured (JSON) logging, configured before anything else logs.
from app.logging_config import configure_logging
configure_logging()

import logging
import os

from fastapi import Depends
from fastapi import FastAPI
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db.database import Base
from app.db.database import engine
from app.db.database import SessionLocal
from app.db.session import get_db

from app.middleware.rate_limit import RateLimitMiddleware
from app.middleware.request_id import RequestIdMiddleware

logger = logging.getLogger("datafe.app")

from app.models.organization import Organization
from app.models.user import User
from app.models.source import DataSource
from app.models.dataset import Dataset
from app.models.column import DatasetColumn
from app.models.lineage import DatasetLineage
from app.models.column_lineage import ColumnLineage
from app.models.governance import BusinessGlossaryTerm
from app.models.data_quality import DataQuality
from app.models.audit_log import AuditLog
from app.models.data_contract import DataContract
from app.models.dataset_view import DatasetView
from app.models.certification_request import CertificationRequest
from app.models.governance_thread import GovernanceThread, GovernanceThreadReply
from app.models.glossary_link import GlossaryTermLink
from app.models.business_process import BusinessProcess, BusinessProcessLink
from app.models.control import Control
from app.models.risk import Risk, RiskDatasetLink, RiskProcessLink, RiskControlLink
from app.models.magic_login_token import MagicLoginToken
from app.models.marketing_event import MarketingEvent



from app.api.auth import router as auth_router
from app.api.users import router as users_router
from app.api.sources import router as source_router
from app.api.datasets import router as dataset_router
from app.api.columns import router as column_router
from app.api.scanner import router as scanner_router
from fastapi.middleware.cors import CORSMiddleware
from app.api.dashboard import router as dashboard_router
from app.api.lineage import router as lineage_router
from app.api.column_lineage import router as column_lineage_router
from app.api.governance import router as governance_router
from app.api.data_quality import router as data_quality_router
from app.api.audit_log import router as audit_log_router
from app.api.privacy import router as privacy_router
from app.api.reports import router as reports_router
from app.api.data_contracts import router as data_contracts_router
from app.api.maturity import router as maturity_router
from app.api.certification_requests import router as certification_requests_router
from app.api.assistant import router as assistant_router
from app.api.governance_threads import router as governance_threads_router
from app.api.demo import router as demo_router
from app.api.glossary_links import router as glossary_links_router
from app.api.business_processes import router as business_processes_router
from app.api.risks import router as risks_router
from app.api.controls import router as controls_router
from app.api.search import router as search_router
from app.api.mentions import router as mentions_router
from app.api.query_log import router as query_log_router
from app.api.platform import router as platform_router
from app.api.marketing import router as marketing_router
from app.api.billing import router as billing_router
from app.api.columns import (
    router as columns_router
)

# Schema is managed by Alembic (see backend/alembic/). create_all() is
# a dev-only convenience for spinning up a scratch DB fast; it must
# stay off anywhere migrations are the source of truth, or Alembic's
# view of "current schema" will silently drift from the real one.
if os.getenv("AUTO_CREATE_SCHEMA", "false").lower() == "true":
    Base.metadata.create_all(bind=engine)


def seed_demo_data():
    db = SessionLocal()

    try:
        if db.query(DataSource).count() == 0:

            organization = db.query(Organization).filter(
                Organization.slug == "demo"
            ).first()

            if organization is None:
                organization = Organization(
                    name="Demo Org",
                    slug="demo"
                )
                db.add(organization)
                db.flush()

            source = DataSource(
                name="Demo PostgreSQL",
                type="postgresql",
                connection_config={
                    "host": "db.example.com",
                    "port": 5432,
                    "database": "sales",
                    "user": "demo"
                },
                organization_id=organization.id
            )
            db.add(source)
            db.flush()

            dataset = Dataset(
                name="customers",
                schema_name="public",
                description="Sample customer dataset for the demo experience",
                ai_summary="Contains customer profile and contact information",
                domain="CRM",
                steward="Alex",
                tags="crm,customers",
                certification="VERIFIED",
                owner="Data Platform",
                source_id=source.id,
                organization_id=organization.id,
            )
            db.add(dataset)
            db.flush()

            db.add_all([
                DatasetColumn(
                    dataset_id=dataset.id,
                    name="customer_id",
                    data_type="integer",
                    nullable=False,
                    classification="PII",
                    sensitivity_score="0.96",
                    confidence=0.98,
                    detection_reason="Primary key",
                    recommendation="Keep restricted"
                ),
                DatasetColumn(
                    dataset_id=dataset.id,
                    name="email",
                    data_type="string",
                    nullable=False,
                    classification="SENSITIVE",
                    sensitivity_score="0.90",
                    confidence=0.95,
                    detection_reason="Contact information",
                    recommendation="Mask in non-prod"
                )
            ])
            db.commit()
    finally:
        db.close()


# Demo seeding is opt-in. It also requires ENCRYPTION_KEY to already
# be set, since DataSource.connection_config is encrypted at rest.
if os.getenv("DEMO_SEED", "false").lower() == "true":
    seed_demo_data()

app = FastAPI(
    title="DataFe",
    version="0.2.0"
)

app.include_router(auth_router)
app.include_router(users_router)
app.include_router(source_router)
app.include_router(dataset_router)
app.include_router(column_router)
app.include_router(scanner_router)
app.include_router(dashboard_router)
app.include_router(lineage_router)
app.include_router(column_lineage_router)
app.include_router(governance_router)
app.include_router(data_quality_router)
app.include_router(audit_log_router)
app.include_router(privacy_router)
app.include_router(reports_router)
app.include_router(data_contracts_router)
app.include_router(maturity_router)
app.include_router(certification_requests_router)
app.include_router(assistant_router)
app.include_router(governance_threads_router)
app.include_router(demo_router)
app.include_router(glossary_links_router)
app.include_router(business_processes_router)
app.include_router(risks_router)
app.include_router(controls_router)
app.include_router(search_router)
app.include_router(mentions_router)
app.include_router(query_log_router)
app.include_router(platform_router)
app.include_router(marketing_router)
app.include_router(billing_router)

# CORS_ALLOWED_ORIGINS is a comma-separated list of exact origins,
# e.g. "https://app.example.com,http://localhost:3000". Wildcard
# ("*") origins combined with allow_credentials=True let any site
# read authenticated responses cross-origin, so the two must never
# be combined - browsers themselves refuse to honor that combination
# for credentialed requests, but the previous config normalized the
# habit and would misbehave the moment credentials were dropped.
_raw_origins = os.getenv("CORS_ALLOWED_ORIGINS", "http://localhost:3000")
ALLOWED_ORIGINS = [
    origin.strip()
    for origin in _raw_origins.split(",")
    if origin.strip()
]

app.add_middleware(RequestIdMiddleware)
app.add_middleware(RateLimitMiddleware)

# CORS is added last so it ends up outermost in the middleware stack -
# it needs to wrap the rate limiter too, or a 429 response wouldn't
# carry CORS headers and the frontend would see it as a generic
# network error instead of a readable "too many requests".
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _health_payload(db: Session) -> dict:

    try:
        db.execute(text("SELECT 1"))
        database_status = "ok"
    except Exception:
        logger.exception("Health check: database connectivity check failed")
        database_status = "error"

    return {
        "status": "running" if database_status == "ok" else "degraded",
        "database": database_status,
        "version": app.version,
    }


@app.get("/")
def root_health(db: Session = Depends(get_db)):
    return _health_payload(db)


@app.get("/health")
def health(db: Session = Depends(get_db)):
    return _health_payload(db)
