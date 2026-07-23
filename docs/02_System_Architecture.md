# System Architecture

## Components

The platform has three main layers:

- FastAPI backend for APIs, scanning, enrichment, governance, lineage, and data quality.
- SQLAlchemy persistence layer with PostgreSQL by default.
- Next.js frontend for catalog, lineage, dataset intelligence, and governance views.

## Request Flow

1. The frontend calls API routes through `/backend`.
2. Next.js rewrites `/backend/:path*` to `http://127.0.0.1:8000/:path*`.
3. FastAPI routers serve the application domains.
4. SQLAlchemy models persist catalog, lineage, quality, and governance data.

## Backend Domains

- Auth: `backend/app/api/auth.py`
- Sources: `backend/app/api/sources.py`
- Scanner: `backend/app/api/scanner.py`
- Datasets: `backend/app/api/datasets.py`
- Columns: `backend/app/api/columns.py`
- Lineage: `backend/app/api/lineage.py`
- Data quality: `backend/app/api/data_quality.py`
- Governance: `backend/app/api/governance.py`
- Dashboard: `backend/app/api/dashboard.py`

## Frontend Domains

- Catalog dashboard: `frontend/src/app/page.tsx`
- Dataset detail: `frontend/src/app/datasets/[id]/page.tsx`
- Lineage graph: `frontend/src/app/lineage/page.tsx`
- Governance workspace: `frontend/src/app/governance/page.tsx`
