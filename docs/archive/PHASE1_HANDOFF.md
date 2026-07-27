# Phase 1 — Compliance Wedge: Privacy Engine & Real Data Quality

Date: 2026-07-22
Author: Claude (Cowork), on request from Soumick
Builds on: PHASE0_HANDOFF.md (auth, multi-tenancy, encryption, Alembic)

## What changed

**Privacy engine is real, and wired in.**
- `app/utils/privacy_engine.py` was rewritten. Its regex constants
  (email, phone, Aadhaar, PAN) existed before but were never actually
  used against real data - `analyze_column` only looked at column
  *names*. It now also samples up to 20 real values per column
  (collected during the scan, see below) and checks them against the
  patterns, in both directions: a generic column name like `contact`
  gets classified from its values, and a column named `email` whose
  values *don't* look like emails (e.g. `email_template_id`) has its
  confidence and sensitivity score lowered instead of blindly trusting
  the name.
- Added DPDP/GDPR-relevant categories beyond generic PII: `financial`
  (bank account, IFSC, cards), `health`, `biometric`,
  `government_id` (Aadhaar, PAN, passport, voter ID),
  `sensitive_personal` (religion, caste, sexual orientation - DPDP's
  higher-consent-bar categories), and `identity` (DOB, gender, name).
- `sensitivity_score` is now a float in `[0, 1]` instead of a
  `"HIGH"/"MEDIUM"/"LOW"` string, so it can actually be sorted/averaged.
  A `risk_level` label is still returned for display.
- New `consent_required` boolean per column - the starting point for
  an actual consent/purpose-limitation feature later.
- `scanner.py` now calls `analyze_column`. The old, weaker,
  name-only `utils/classifier.py` (which scanner.py used to call
  instead) is deleted rather than left as a second, competing
  classification system.

**The destructive rescan bug is fixed.**
- Previously: every rescan deleted *all* of a dataset's columns and
  recreated them from scratch, silently destroying any steward
  correction.
- Now (`_sync_columns` in `scanner.py`): columns are diffed by name.
  A column a steward manually classified (`classification_source ==
  "MANUAL"`) keeps its classification, sensitivity score, and
  consent flag across rescans - only its objective schema facts
  (data type, nullable) refresh, since those aren't judgment calls.
  Auto-classified columns get re-run through the privacy engine every
  scan. Columns genuinely dropped from the source table are removed;
  new ones are added. There's no steward-editing UI/endpoint yet -
  this lays the groundwork (`classification_source`) for one.

**Data quality scoring is computed from real numbers, not `random.randint`.**
- `postgres_scanner.py` now collects, per table, during the same scan
  (no extra round-trips to the source DB): row count, per-column
  non-null/distinct counts, and up to 20 sampled values per column.
- `data_quality_service.py` computes completeness (non-null ratio),
  uniqueness (distinct ratio), validity (sampled values matching the
  pattern their column name implies - reuses the privacy engine's
  regexes), and consistency (sampled values of numeric-typed columns
  actually parsing as numbers) from that real data. Freshness is 100
  at scan time by definition; ongoing staleness is tracked separately
  via the existing `Dataset.freshness_status` property.
- Along the way this fixed a pre-existing contract bug:
  `postgres_scanner.scan_postgres_source` used to return a plain list,
  but `scanner.py` and `lineage.py` both indexed it as
  `scan_result["datasets"]` / `scan_result["foreign_keys"]` - which
  would have raised a `TypeError` on any real scan. It now actually
  returns that dict shape, so the scan endpoint works for the first
  time rather than crashing on line one of processing results.

**Retention/consent metadata (schema only - no UI yet).**
- `Dataset.retention_period_days` / `retention_notes`.
- `DatasetColumn.dpdp_category`, `consent_required`,
  `classification_source`.

**Data quality API routes** (`api/data_quality.py`,
`schemas/data_quality.py` were empty files before this):
- `GET /api/data-quality/` - org-scoped list.
- `GET /api/data-quality/dataset/{id}` - single dataset, 404 if it
  doesn't exist or belongs to another org.

**New Alembic migration** (`fd37165e7d99_phase1_privacy_and_retention_metadata.py`,
chained after Phase 0's `6e9ba7d34bd6`): adds the 5 new columns above.
Verified with a real `upgrade head` / `downgrade -1` cycle.

## What did NOT change

- No frontend work (still Phase 0's known gap).
- No steward-facing endpoint to actually set `classification_source =
  "MANUAL"` yet - the column exists and the scanner respects it, but
  today it can only be set by editing the DB directly. Natural next
  step once there's a UI for reviewing classifications.
- Retention/consent fields are columns with no enforcement or workflow
  behind them yet (no automated deletion at retention expiry, no
  consent capture flow). This phase is schema + classification, not a
  full DPDP compliance program.

## Verification

23/23 tests pass (`pytest tests/ -v`), including:
- `test_privacy_engine.py` - name/value agreement and disagreement,
  DPDP category assignment, numeric score bounds.
- `test_data_quality_service.py` - hand-computed expected ratios
  (e.g. 3 non-null out of 4 rows -> exactly 75.0), proving the scores
  are arithmetic, not randomness, plus a determinism check (profiling
  the same input twice gives identical output).
- `test_scan_column_diffing.py` - drives two real scans through the
  full FastAPI app (only the Postgres connection itself is mocked):
  proves a manually-overridden column survives a rescan unchanged
  while a dropped column is removed and a new column is added in the
  same pass, and that the resulting data-quality profile reflects the
  real (mocked) row/column stats.
- Alembic `upgrade head` / `downgrade -1` verified against a scratch
  SQLite DB.

## How to apply

Same as Phase 0: no push access to the GitHub repo from this
environment. `phase1-privacy-quality.patch` applies on top of a
checkout that already has Phase 0 applied
(`git apply phase1-privacy-quality.patch`). `metadata-platform-phase0.zip`
in this delivery already includes both phases combined if you'd
rather just copy the full `backend/` over your working copy.

```bash
cd backend
alembic upgrade head   # picks up both migrations if starting fresh
pytest tests/ -v
```
