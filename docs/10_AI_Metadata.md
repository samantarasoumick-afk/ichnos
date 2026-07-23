# AI Metadata

AI metadata enrichment is implemented through:

- `backend/app/services/ai_metadata_service.py`
- `backend/app/utils/ai_enrichment.py`

## Current Capabilities

- Dataset descriptions
- Dataset summaries
- Scanner integration for newly discovered metadata

## Product Direction

AI enrichment should remain explainable and grounded in catalog facts. Future copilot answers should cite datasets, columns, lineage, classifications, quality, and governance state rather than inventing unsupported conclusions.

## Next Work

- Store generated metadata provenance.
- Add regeneration controls.
- Add confidence and review state.
- Feed glossary terms into AI summaries.
