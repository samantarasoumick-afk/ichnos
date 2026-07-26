# Data Quality

Data quality profiling is implemented through:

- Model: `backend/app/models/data_quality.py`
- Service: `backend/app/services/data_quality_service.py`
- Scanner integration: `backend/app/api/scanner.py`

## Current Metrics

- Completeness
- Uniqueness
- Validity
- Freshness
- Consistency
- Overall score

## Product Role

Quality contributes to dataset trust and operational status, and
feeds the governance score when quality drops below the expected
threshold. Scores are also blended with lineage: a dataset's
*effective* quality score factors in how well-documented its upstream
transformations are (see `docs/07_Lineage.md`), computed by
`backend/app/services/lineage_quality_service.py` and exposed via the
`/api/data-quality/effective` bulk endpoint. A catalog-wide Data
Quality page (`frontend/src/app/data-quality/page.tsx`) surfaces every
dataset's effective score sorted worst-first, with domain/threshold
filters, so problem datasets don't require opening each one
individually.

## Next Work

- Persist rule definitions (thresholds are currently computed, not
  independently configurable per org).
- Add dataset-level quality history / trend lines - today's score is
  point-in-time only, no historical tracking.
- Add incident creation when quality falls below policy.
- DQ threshold enforcement as part of Data Contracts (currently
  breach *logging* only - see `docs/13_Roadmap.md` Phase 2).
