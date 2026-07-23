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

Quality contributes to dataset trust and operational status. It also affects governance score when quality drops below the expected threshold.

## Next Work

- Persist rule definitions.
- Add dataset-level quality history.
- Show quality trend lines in the frontend.
- Add incident creation when quality falls below policy.
