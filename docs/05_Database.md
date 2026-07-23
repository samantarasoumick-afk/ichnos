# Database

The platform uses SQLAlchemy models under `backend/app/models`.

## Core Tables

- `data_sources`
- `datasets`
- `columns`
- `dataset_lineage`
- `data_quality`
- `business_glossary_terms`
- users table from the auth model

## Dataset Governance Fields

The `datasets` table currently stores:

- `owner`
- `steward`
- `domain`
- `tags`
- `certification`

Governance score is computed from dataset completeness, certification, sensitivity, freshness, and quality state.

## Next Database Work

- Add Alembic migrations.
- Normalize tags into a many-to-many table when tag usage becomes richer.
- Add ownership history and certification audit events.
