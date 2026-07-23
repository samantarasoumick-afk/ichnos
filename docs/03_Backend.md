# Backend

The backend is a FastAPI application in `backend/app`.

## Entry Point

`backend/app/main.py` creates the FastAPI app, initializes tables with SQLAlchemy metadata, seeds demo data when empty, and includes API routers.

## Database Access

Database sessions are provided by `backend/app/db/session.py`. The default database URL is configured in `backend/app/db/database.py`.

## Current Routers

- `/api/auth`
- `/api/sources`
- `/api/datasets`
- `/api/columns`
- `/api/scanner`
- `/api/dashboard`
- `/api/lineage`
- `/api/governance`

## Implementation Notes

The backend currently uses computed SQLAlchemy model properties for catalog intelligence, including risk, trust, freshness, quality, operational status, and governance score.

As the product matures, database migrations should replace `Base.metadata.create_all` as the main schema management approach.
