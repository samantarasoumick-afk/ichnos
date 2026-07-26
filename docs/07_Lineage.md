# Lineage

Lineage captures upstream and downstream dataset relationships two
ways: automatic discovery from PostgreSQL foreign keys, and manually-
documented edges (transformation type, description, filter logic) for
everything a source's own metadata can't express. Column-level
lineage is also implemented. A lineage-adjusted data quality score
blends a dataset's own DQ score with how well its upstream
transformations are documented, so well-documented pipelines are
trusted more than a black box with the same raw quality numbers.

**Known limitation, worth being upfront about**: automatic discovery
depends on FK constraints existing in the source, which many
warehouses and dbt-modeled marts don't enforce. Outside of FK-covered
sources and the dbt-artifact-upload path, lineage completeness
currently depends on someone manually documenting edges - there's no
automated SQL/dbt-model parsing yet for arbitrary transformation code.

## Backend

- Model: `backend/app/models/lineage.py`
- API: `backend/app/api/lineage.py`
- Discovery service: `backend/app/services/lineage_discovery.py`
- Service helpers: `backend/app/services/lineage_service.py`
- Lineage-adjusted DQ scoring: see `docs/08_Data_Quality.md`

## Frontend

`frontend/src/app/lineage/page.tsx` renders lineage using
`frontend/src/components/LineageGraph.tsx` - searchable, with a
reactive dataset dropdown. Column-level lineage also surfaces on the
dataset detail page's Lineage tab.

## Next Work

- Automated SQL/dbt-model parsing for lineage discovery beyond FK
  relationships and dbt artifact upload (currently the main
  completeness gap - see "Known limitation" above).
- Impact analysis APIs for AI copilot workflows.
- Lineage breach propagation for Data Contracts (see `docs/13_Roadmap.md`).
