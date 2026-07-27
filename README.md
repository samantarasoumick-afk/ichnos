# DataFe

[![CI](https://github.com/samantarasoumick-afk/ichnos/actions/workflows/ci.yml/badge.svg)](https://github.com/samantarasoumick-afk/ichnos/actions/workflows/ci.yml)

**DataFe** is a metadata intelligence platform - a searchable, living
catalog that turns messy tables, tangled pipelines, and forgotten
spreadsheets into a self-explaining map of a company's data, with
lineage, data quality, and governance built in rather than bolted on.

Live at [datafetech.com](https://datafetech.com) (marketing site) /
[app.datafetech.com](https://app.datafetech.com) (the app).

> The GitHub repo is still named `ichnos` - that's DataFe's original
> product name before a rebrand; the code and product itself are
> DataFe throughout. Renaming the repo itself is on the backlog.

## What it does

- **Catalog & discovery** - source registration and scanning across
  Postgres, MySQL, Snowflake, Redshift, S3, Azure SQL/Synapse, dbt,
  Tableau, Stripe, and CSV upload, with AI-generated descriptions and
  auto data classification.
- **Lineage** - automatic FK-based discovery plus manually-documented
  transformations, feeding a lineage-adjusted data quality score.
- **Data quality** - real profiling from scan-time statistics, not
  simulated numbers.
- **Governance** - business glossary, process repository, data
  contracts, certification workflow, risk register, audit log,
  governance discussions, and a maturity score.
- **Privacy** - DPDP/GDPR-oriented classification, consent tracking,
  retention enforcement, compliance reporting.
- **Platform** - multi-tenant RBAC, per-plan entitlements, Stripe
  self-serve billing, a platform-admin dashboard, and an NL Q&A
  assistant grounded in the catalog itself.

See `docs/13_Roadmap.md` for the full delivered list and what's still
open before wider rollout.

## Repo layout

```
backend/    FastAPI + SQLAlchemy + Alembic (Python)
frontend/   Next.js 16 + React 19 (TypeScript)
website/    Static marketing site, served by nginx
docs/       Numbered reference docs - start with 01_Project_Overview.md
```

## Quickstart (local dev)

```bash
cp .env.example .env
# edit .env: at minimum set POSTGRES_PASSWORD, SECRET_KEY, ENCRYPTION_KEY
docker compose up -d --build
```

Then open `http://localhost` (marketing site) or `http://app.localhost`
(the app). See `docs/12_Developer_Guide.md` for running the backend/
frontend outside Docker, and `docs/SELF_HOSTING.md` for taking this
further than your own machine.

## Documentation map

| Doc | Covers |
|---|---|
| `docs/01_Project_Overview.md` | What this is, for whom |
| `docs/02_System_Architecture.md` | How the pieces fit together |
| `docs/03_Backend.md` / `04_Frontend.md` / `05_Database.md` | Per-layer detail |
| `docs/06_Metadata_Scanner.md` - `10_AI_Metadata.md` | Feature-area deep dives |
| `docs/11_API_Reference.md` | Endpoint reference |
| `docs/12_Developer_Guide.md` | Local dev commands |
| `docs/13_Roadmap.md` | Delivered vs. open, phased rollout gates |
| `docs/14_CI_CD_and_Environments.md` | Branch strategy, dev vs. prod, deploy process |
| `docs/SELF_HOSTING.md` | Getting this running on real infrastructure |
| `docs/SECURITY_REVIEW.md` | Security review findings and status |

## Contributing / working on this

- Active development happens on `main`; `production` is the deployed
  branch - see `docs/14_CI_CD_and_Environments.md` before pushing
  straight to `production`.
- Run backend tests: `cd backend && python -m pytest -q`
- Run frontend checks: `cd frontend && npx tsc --noEmit && npx eslint
  src && npm run build`
- Both run automatically in CI on every push/PR to `main` or
  `production`.
