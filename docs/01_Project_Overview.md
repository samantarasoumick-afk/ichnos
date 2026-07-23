# Project Overview

The Metadata Intelligence Platform is a FastAPI and Next.js application for discovering, cataloging, governing, and monitoring enterprise data assets.

## Current Product Stage

Phase 1, Metadata Discovery, is mostly implemented:

- Data source registration
- PostgreSQL metadata scan
- Dataset and column catalog
- AI-generated descriptions and summaries
- Column classification
- Foreign-key lineage discovery
- Data quality profiling
- Dashboard and dataset detail screens

Phase 2, Governance, has started:

- Dataset owners, stewards, domains, tags, and certifications
- Governance score calculation
- Governance overview and scorecard APIs
- Business glossary model and API
- Governance frontend workspace

## Architecture Snapshot

- Backend: `backend/app`
- Frontend: `frontend/src`
- Infrastructure: `infra/docker-compose.yml`
- Documentation: `docs`

## Operating Principle

Build in milestones. Each phase should expose a coherent product capability, not only isolated endpoints.
