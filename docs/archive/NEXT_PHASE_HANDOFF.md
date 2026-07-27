# Next Phase — Compliance Trust Layer (Audit Trail, Consent, Retention, Privacy Score)

Date: 2026-07-22
Author: Claude (Cowork), on request from Soumick
Builds on: PHASE0_HANDOFF.md, PHASE1_HANDOFF.md

This covers the four "Next"-priority items from the reconciled master
roadmap: audit trail, purpose mapping/consent tracking, retention
policy enforcement, and a privacy dashboard/score. Together these turn
the Phase 1 privacy engine's raw classifications into something a
pilot customer can actually see and act on.

## What changed

**Audit trail** (`models/audit_log.py`, `services/audit_service.py`,
`api/audit_log.py`).
- Append-only `audit_logs` table: org, actor, action, resource
  type/id, free-text details, timestamp. Nothing in the API updates
  or deletes a row here.
- Logged so far: `user.register`, `user.login`, `source.create`,
  `scanner.scan`, `governance.update`, `governance.certify`,
  `governance.tag`, `glossary.create`. `log_audit_event()` doesn't
  commit on its own - it's added to the same transaction as the
  action it's describing, so the log entry and the action succeed or
  fail together.
- `GET /api/audit-log/` - org-scoped, most recent first, capped at
  500 rows per request.

**Purpose mapping + consent tracking** (`models/dataset.py`).
- `Dataset.purpose` (free text - why this data is processed) and
  `Dataset.consent_status` (`NOT_ASSESSED` default /
  `CONSENT_OBTAINED` / `CONSENT_NOT_REQUIRED`). Both are steward
  judgment calls, not something the scanner infers - a column
  containing an email address doesn't tell you whether consent was
  actually collected for it.
- Settable via the existing `PATCH /api/governance/datasets/{id}`
  endpoint (extended, not a new endpoint).

**Retention policy enforcement** (`models/dataset.py`).
- `Dataset.created_at` added (previously only `last_scanned_at`
  existed, which updates on every rescan and isn't the right
  reference point for "how long have we held this data").
- `Dataset.retention_status` computed property: `NOT_SET` /
  `WITHIN_POLICY` / `OVERDUE`, based on `retention_period_days` vs.
  age. This flags overdue data; it does not delete or restrict
  anything automatically - no auto-deletion job exists yet.

**Privacy dashboard / score** (`models/dataset.py` property,
`api/privacy.py`).
- `Dataset.privacy_score` (0-100, same style as the existing
  `governance_score`/`trust_score`/`quality_score` properties):
  datasets with no columns requiring consent score 100 by default;
  datasets that do get scored down for unassessed consent (-30),
  missing purpose (-15), overdue retention (-25) or no retention
  policy at all (-10), and low-confidence classifications on
  high-risk categories like health/biometric/government ID (-10).
  Deterministic and tested, not a placeholder.
- `GET /api/privacy/overview` - org-wide average privacy score,
  counts of datasets needing consent review / missing purpose /
  overdue retention, a breakdown of sensitive columns by DPDP
  category, and the 5 lowest-scoring ("top at-risk") datasets. This
  is the single screen that makes the DPDP compliance wedge visible
  to a pilot customer instead of living only in per-column database
  rows.

**New Alembic migration**
(`18e3f127bef9_audit_log_purpose_consent_retention_.py`, chained after
Phase 1's `fd37165e7d99`): creates `audit_logs`, adds `created_at`,
`purpose`, `consent_status` to `datasets`. Verified with a real
`upgrade head` / `downgrade -1` cycle.

## What did NOT change / known gaps

- No UI for any of this - it's all API surface. The frontend still
  has no auth wiring at all (flagged in Phase 0), so none of Phase 0/1/
  this phase's work is reachable from the existing Next.js app yet.
- No automated retention enforcement (e.g. a scheduled job that
  actually deletes/archives overdue data) - `retention_status` is a
  flag, not an action.
- No consent *capture* flow (e.g. a form a data subject fills out) -
  `consent_status` is a steward's manual attestation.
- Audit log has no UI/export and isn't yet linked to specific
  governance field-level diffs (it records "which fields changed",
  not old-value/new-value pairs).

## Verification

39/39 tests pass (`pytest tests/ -v`), 16 of them new for this phase:
- `test_privacy_score.py` - hand-computed expected scores for each
  deduction (e.g. unassessed consent alone -> exactly 70), plus a
  floor-at-zero check and retention-status edge cases (missing
  `created_at` falls back to `last_scanned_at`).
- `test_audit_and_privacy_api.py` - drives real HTTP requests through
  the full app: register/login/source-create/scan are all confirmed
  present in the audit log, a second org's audit log is confirmed to
  never show the first org's events (tenant isolation, same as
  everything else), and the privacy overview endpoint is confirmed to
  reflect real scanned PII (an email column drags the average score
  below 100 and shows up under the `contact` DPDP category) before
  and after a governance update sets purpose/consent/retention.
- Alembic `upgrade head` / `downgrade -1` verified against a scratch
  SQLite DB.

## How to apply

Same delivery constraint as before - no push access to the GitHub
repo from this environment. `next-phase-compliance-trust.patch`
applies on top of a checkout with Phase 0 and Phase 1 already applied.
`metadata-platform-phase0-1.zip`... update: use the newly attached zip
which now includes all three phases combined if you'd rather copy
`backend/` wholesale.

```bash
cd backend
alembic upgrade head   # picks up all three migrations if starting fresh
pytest tests/ -v
```
