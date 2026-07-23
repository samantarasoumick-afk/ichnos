# Lineage

Lineage currently captures upstream and downstream dataset relationships, primarily discovered from PostgreSQL foreign keys.

## Backend

- Model: `backend/app/models/lineage.py`
- API: `backend/app/api/lineage.py`
- Discovery service: `backend/app/services/lineage_discovery.py`
- Service helpers: `backend/app/services/lineage_service.py`

## Frontend

`frontend/src/app/lineage/page.tsx` renders lineage using `frontend/src/components/LineageGraph.tsx`.

## Next Work

- Manual lineage edits.
- Transformation metadata.
- Column-level lineage.
- Impact analysis APIs for AI copilot workflows.
