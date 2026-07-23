# Governance

Governance is Phase 2 of the platform and is now started.

## Implemented

- Dataset owner, steward, domain, tags, and certification fields.
- Governance status computed on each dataset.
- Governance score computed on each dataset.
- Governance overview API.
- Dataset scorecard API.
- Dataset governance update API.
- Certification update API.
- Tag update API.
- Business glossary table and API.
- Governance frontend page.

## Backend API

Base path:

```text
/api/governance
```

Endpoints:

- `GET /overview`
- `GET /scorecards`
- `GET /datasets/{dataset_id}/scorecard`
- `PATCH /datasets/{dataset_id}`
- `PATCH /datasets/{dataset_id}/certification`
- `PATCH /datasets/{dataset_id}/tags`
- `GET /glossary`
- `POST /glossary`
- `PATCH /glossary/{term_id}`

## Governance Score

The score starts at 100 and deducts points for missing ownership, missing stewardship, missing domain, missing description, missing tags, non-verified certification, high sensitivity, stale scans, and weak quality.

## Next Work

- Steward assignment UI.
- Glossary create and edit UI.
- Certification workflow states.
- Ownership audit history.
- Dataset policy badges.
