# Project Overview

The Metadata Intelligence Platform is a FastAPI and Next.js application for discovering, cataloging, governing, and monitoring enterprise data assets.

## Current Product Stage

**For the authoritative, currently-maintained status of what's built and
what's left, see `docs/13_Roadmap.md`.** The sections below describe
each subsystem's design and are updated less frequently than the
roadmap - if the two ever disagree, trust the roadmap.

In brief: metadata discovery (9+ source connectors, AI-generated
descriptions, column classification, lineage, data quality profiling)
and governance (glossary, business processes, data contracts,
certification workflow, maturity scoring, risk register, audit log,
discussions) are both substantially built out - not just started. See
`docs/13_Roadmap.md`'s "Delivered" section for the full, current list,
and its "Rollout-readiness verdict" for what's left before this is
safe to hand to external users with real data.

## Architecture Snapshot

- Backend: `backend/app`
- Frontend: `frontend/src`
- Infrastructure: `infra/docker-compose.yml`
- Documentation: `docs`

## Operating Principle

Build in milestones. Each phase should expose a coherent product capability, not only isolated endpoints.
