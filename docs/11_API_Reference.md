# API Reference

## Sources

- `GET /api/sources`
- `POST /api/sources`

## Scanner

- `POST /api/scanner/{source_id}`

## Datasets

- `GET /api/datasets`
- `GET /api/datasets/{dataset_id}`
- `GET /api/datasets/{dataset_id}/summary`

## Columns

- `GET /api/columns`
- `GET /api/columns/dataset/{dataset_id}`

## Lineage

- `GET /api/lineage`

## Dashboard

- `GET /api/dashboard/overview`

## Governance

- `GET /api/governance/overview`
- `GET /api/governance/scorecards`
- `GET /api/governance/datasets/{dataset_id}/scorecard`
- `PATCH /api/governance/datasets/{dataset_id}`
- `PATCH /api/governance/datasets/{dataset_id}/certification`
- `PATCH /api/governance/datasets/{dataset_id}/tags`
- `GET /api/governance/glossary`
- `POST /api/governance/glossary`
- `PATCH /api/governance/glossary/{term_id}`
