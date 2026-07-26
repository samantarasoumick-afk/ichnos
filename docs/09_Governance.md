# Governance

Governance is the most built-out subsystem in the platform. Beyond the
original dataset-level fields and scoring described below, it now
includes: a Business Glossary with dataset/column-level term linking
(and terms auto-created/reused when a dataset is linked to a Business
Process, so the glossary builds itself instead of needing separate
upkeep); a Process Repository with plain-language narrative fields and
Master/Reference/Transactional/Analytical grouping; Data Contracts
(schema-level, with breach logging - DQ threshold enforcement and
lineage breach propagation are still open, see `docs/13_Roadmap.md`);
a certification request/approval workflow; a governance maturity score
(org-level, multiple dimensions including risk coverage, with
recommendations - currently point-in-time, no trend history yet); a
risk register (likelihood x impact, linked to datasets/processes) with
a reusable control library; governance discussion threads (Question /
Proposal / Issue types, the last with stakeholder follow-through); and
an audit log with filtering and CSV export.

## Implemented

- Dataset owner, steward, domain, tags, and certification fields.
- Governance status and score computed on each dataset.
- Governance overview, scorecard, glossary, business process, data
  contract, certification, maturity, risk/control, and discussion
  APIs - each with its own frontend page or panel.
- Data Owner role (RBAC), scoped to approval workflows - no masking
  capability yet (see `docs/13_Roadmap.md`).

## Backend API

Base path:

```text
/api/governance
```

Core endpoints (non-exhaustive - see `docs/11_API_Reference.md` for
the full surface across governance, glossary, processes, contracts,
risks/controls, and discussions):

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

- Masking capability for sensitive columns (Data Owner role is
  currently approval-only).
- Data Contract enforcement beyond logging: DQ threshold checks and
  lineage breach propagation.
- Role-differentiated landing experiences - Data Owner approval queue,
  Steward stewardship-gap view, Viewer simplified discovery view.
  Backend RBAC already supports this; no page currently reflects it.
- Steward assignment / triage queue (gaps are visible in scoring, not
  yet routed to anyone).
- Governance maturity trend snapshots (currently point-in-time only).
- Broader role model redesign as real usage surfaces gaps in the
  current four roles.
