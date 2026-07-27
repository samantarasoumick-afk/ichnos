# Phase 0 — Security & Multi-Tenant Foundation

Date: 2026-07-22
Author: Claude (Cowork), on request from Soumick

## Why

The previous audit found the live repo had none of the hardening that
project notes claimed was done: no auth enforcement on mutation
routes, CORS set to wildcard-plus-credentials, plaintext DB
credentials in `connection_config`, no Alembic, and no tenant concept
at all despite the product being scoped as multi-tenant SaaS. This
phase closes those gaps before any pilot customer connects a real
database.

## What changed

**Auth is now enforced, not decorative.**
- `app/auth/jwt_handler.py` gained `decode_access_token()` — tokens
  are actually verified now, not just issued.
- `app/auth/dependencies.py` (new) provides `get_current_user` and
  `require_role(*roles)`. Every mutation route now depends on one of
  these; read routes require `get_current_user` at minimum.
- `SECRET_KEY` no longer has a hardcoded fallback — the app refuses
  to start without one set in the environment.

**Multi-tenancy.**
- New `Organization` model (`app/models/organization.py`).
- `User`, `DataSource`, `Dataset`, `BusinessGlossaryTerm` all gained
  `organization_id`. Every query in `sources.py`, `scanner.py`,
  `datasets.py`, `columns.py`, `lineage.py`, `governance.py`,
  `dashboard.py` is filtered by `current_user.organization_id`.
- `POST /api/auth/register` now takes `organization_name`, creates a
  new `Organization`, and makes the first user its `admin`. There is
  no invite flow yet — every signup is a new org (fine for MVP,
  revisit before this multiplies orgs unnecessarily).
- Cross-tenant lookups return `404`, not `403` — an org shouldn't be
  able to tell that another tenant's resource ID exists at all.

**Credentials encrypted at rest.**
- `app/utils/crypto.py` + `app/db/encrypted_types.py`: a Fernet-backed
  `EncryptedJSON` SQLAlchemy type. `DataSource.connection_config` uses
  it, so the raw DB bytes never contain plaintext host/user/password —
  verified directly in the test suite by scanning the SQLite file for
  the plaintext marker.
- Requires `ENCRYPTION_KEY` in the environment. **Losing this key
  makes every stored source credential unreadable — back it up like
  you would a database password.**

**CORS.**
- `allow_origins=["*"]` + `allow_credentials=True` (the specific
  misconfiguration flagged in the audit) is gone. Origins now come
  from `CORS_ALLOWED_ORIGINS` (comma-separated), defaulting to
  `http://localhost:3000` for local dev.

**Alembic.**
- `backend/alembic/` is wired to `app.db.database.Base` and reads
  `DATABASE_URL` from the environment (no connection string lives in
  `alembic.ini`).
- One hand-reviewed initial migration
  (`alembic/versions/6e9ba7d34bd6_*.py`) creates all 8 tables,
  including the new `organizations` table and every `organization_id`
  FK. Verified with a real `upgrade head` / `downgrade base` cycle
  against a scratch SQLite DB (see below).
- `Base.metadata.create_all()` in `main.py` is now gated behind
  `AUTO_CREATE_SCHEMA=true` (default off) — Alembic is the source of
  truth for schema everywhere that flag isn't set.

**Tests.**
- `backend/tests/test_auth_tenant_isolation.py` (new): registration,
  login, unauthenticated rejection, cross-tenant isolation on sources
  + glossary + scan-triggering, credential encryption round-trip, and
  viewer-role read-only enforcement. 6/6 tests pass including the
  pre-existing scanner test (unaffected).

## What did NOT change (intentionally out of scope for Phase 0)

- The destructive column-rescan bug, privacy_engine wiring, and the
  empty data-quality routes are Phase 1 (compliance wedge) work per
  the roadmap discussed — untouched here.
- No frontend changes. The Next.js app has no login screen or auth
  header wiring yet, so it will get 401s from every API call until
  that's built. That's the natural next slice of Phase 0 if you want
  the UI usable again before starting Phase 1.
- No invite-a-teammate flow — every registration creates a brand new
  org. Fine for solo/pilot use, worth flagging before it's used by
  a team of more than one.

## How to run this

```bash
cd backend
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# fill in SECRET_KEY, ENCRYPTION_KEY, DATABASE_URL, CORS_ALLOWED_ORIGINS
# (.env.example has the exact commands to generate SECRET_KEY / ENCRYPTION_KEY)

alembic upgrade head
uvicorn app.main:app --reload
```

Run the test suite:

```bash
cd backend
pytest tests/ -v
```

## How this was verified

- `alembic upgrade head` then `alembic downgrade base` against a
  scratch SQLite DB — both directions run cleanly, all 8 tables
  appear/disappear correctly.
- Full FastAPI app boot + `TestClient` exercising real HTTP requests
  end-to-end: two orgs registered, sources created, cross-tenant reads
  and scan-triggering attempted and confirmed blocked, viewer role
  confirmed read-only, and the raw SQLite file bytes inspected to
  confirm no plaintext credential is stored anywhere on disk.
- `python -m py_compile` across every touched module.

## Delivery note

I don't currently have push access to
`github.com/samantarasoumick-afk/metadata-platform` (no GitHub
connector is set up in this environment), so this is delivered as a
patch + a full copy of the updated `backend/` rather than a commit or
PR. Apply the patch against a clean checkout of `main`, or copy
`backend/` over your working copy, then review the diff before
pushing. Connect a GitHub MCP connector if you'd like me to open PRs
directly next time.
