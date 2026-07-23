# Frontend

The frontend is a Next.js application in `frontend`.

## Main Screens

- `/`: metadata dashboard with sources, catalog search, dataset cards, and KPI tiles.
- `/datasets/[id]`: dataset detail page with intelligence summary and column classification.
- `/lineage`: lineage visualization built with React Flow.
- `/governance`: governance overview, dataset scorecards, and business glossary.

## API Client

`frontend/src/services/api.ts` defines an Axios client with:

```ts
baseURL: "/backend"
```

Next.js rewrites this to the FastAPI backend.

## Types

Shared frontend metadata types live in `frontend/src/types/metadata.ts`.
