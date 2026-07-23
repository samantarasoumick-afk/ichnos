# Metadata Platform Handoff

Date: 2026-07-09

## Current Project Shape

This workspace contains a metadata intelligence platform with:

- A FastAPI backend in `backend/`
- A Next.js frontend in `frontend/`
- Docker Compose configuration in `infra/docker-compose.yml`

The frontend Git repository is rooted at:

```text
/Users/soumicks/metadata-platform/frontend
```

The top-level `/Users/soumicks/metadata-platform` directory itself is not a Git repository.

## What Was Inspected

The app was reviewed for whether it was ready and whether the recent work looked good.

Initial findings:

- The frontend had moved from `app/` to `src/app/`, but the old `app/` files were deleted in Git.
- The lineage route was broken because `src/app/Lineage/page.tsx` was empty.
- `src/components/LineageGraph.tsx` was also empty.
- The dashboard linked to `/lineage`, but the folder was named `Lineage`, creating a casing mismatch.
- There were accidental empty root files in the frontend:
  - `frontend/next`
  - `frontend/frontend@0.1.0`
- The dashboard had malformed Tailwind classes: `grid grid grid -cols-5`.
- “Operational Alerts” was rendered inside every dataset row instead of once in the dashboard summary.
- `operational_status` was typed as a number in the frontend, but the UI compared it to string values like `UNSTABLE`, `AT_RISK`, and `DEGRADED`.
- The backend dataset schema exposed `Quality_score`, but the frontend expected `quality_score`.
- `ai_summary` was used by the dataset detail page but was missing from the frontend `Dataset` type.

## Changes Made

### Frontend

Added a real lowercase lineage route:

```text
frontend/src/app/lineage/page.tsx
```

The page now:

- Fetches datasets from `/api/datasets`
- Fetches lineage records from `/api/lineage`
- Shows a loading state
- Shows an error state if the backend is not running
- Shows an empty state when no lineage relationships exist
- Renders a graph when lineage data exists
- Includes a link back to the dashboard

Implemented the lineage graph component:

```text
frontend/src/components/LineageGraph.tsx
```

The graph uses React Flow and renders:

- Dataset nodes
- Directed lineage edges
- Edge labels based on `transformation_type`
- Mini map
- Controls
- Background grid

Updated the app layout:

```text
frontend/src/app/layout.tsx
```

Imported React Flow styles:

```ts
import "reactflow/dist/style.css";
```

Updated frontend metadata types:

```text
frontend/src/types/metadata.ts
```

Added:

- `OperationalStatus`
- `Lineage`
- `ai_summary`

Fixed:

- `operational_status` from `number` to the correct string union type

Cleaned up the dashboard:

```text
frontend/src/app/page.tsx
```

Changes:

- Added `isOperationalAlert`
- Fixed malformed grid classes
- Made the summary card grid responsive
- Added an “Operational Alerts” summary card
- Removed the repeated “Operational Alerts” card from inside every dataset row
- Kept the dashboard link pointing to `/lineage`

Deleted accidental empty files:

```text
frontend/next
frontend/frontend@0.1.0
```

Fixed the route casing on disk:

```text
frontend/src/app/Lineage
```

was renamed to:

```text
frontend/src/app/lineage
```

### Backend

Updated the dataset response schema:

```text
backend/app/schemas/dataset.py
```

Changes:

- Added `source_id`
- Fixed `Quality_score` to `quality_score`
- Changed `operational_status` default from `0` to `None`

This better matches the frontend and the SQLAlchemy model properties.

## Verification Completed

The following checks passed:

```bash
npm run lint
```

```bash
npm run build
```

```bash
python3 -m py_compile $(find backend/app -name '*.py')
```

The final Next.js build reports the expected app routes:

```text
/
/_not-found
/datasets/[id]
/lineage
```

The frontend dev server was started successfully at:

```text
http://localhost:3000
```

Browser verification was performed:

- Dashboard loaded successfully
- Dashboard had exactly one `/lineage` link
- `/lineage` loaded successfully
- Because the backend server was not running, `/lineage` showed the expected backend-unavailable message instead of crashing

Screenshot saved at:

```text
/private/tmp/metadata-lineage-check.png
```

## Current Git Status Notes

The frontend repository still shows the move from old root `app/` files to the new `src/app/` structure.

Current frontend Git status included:

```text
D app/favicon.ico
D app/globals.css
D app/layout.tsx
D app/page.tsx
M next.config.ts
M package-lock.json
M package.json
?? src/
```

This means the new source files are currently untracked as a directory from Git's perspective.

Before committing, review and stage the intended files from `src/`, plus package/config changes.

## Known Remaining Work

Suggested next steps:

1. Start and verify the backend server.
2. Confirm all API endpoints return the expected shapes:
   - `/api/datasets`
   - `/api/lineage`
   - `/api/sources`
   - `/api/columns/dataset/{id}`
3. Add or seed lineage data so the graph renders real relationships.
4. Consider adding tests for:
   - Dataset schema response shape
   - Lineage API response shape
   - Frontend dashboard rendering
   - Frontend lineage empty/error/success states
5. Clean up frontend styling and spacing for a more polished product feel.
6. Decide whether the old root `app/` deletion is intentional and stage accordingly.
7. Consider adding `.next/`, virtualenvs, SQLite DB files, and build artifacts to ignore rules if not already ignored at the relevant repo boundaries.

## Important Context For Continuing

The frontend uses:

- Next.js 16.2.6
- React 19.2.4
- React Flow
- Axios
- Tailwind CSS

The frontend API client is:

```text
frontend/src/services/api.ts
```

It uses:

```ts
baseURL: "/backend"
```

The Next rewrite in:

```text
frontend/next.config.ts
```

forwards:

```text
/backend/:path*
```

to:

```text
http://127.0.0.1:8000/:path*
```

So the backend should be running on:

```text
http://127.0.0.1:8000
```

for the frontend to load live data.

## Summary

The main broken pieces were fixed:

- The frontend now builds.
- The lowercase `/lineage` route exists and loads.
- The graph component is implemented.
- The dashboard layout issues were cleaned up.
- Frontend and backend schema/type mismatches were corrected.

The next meaningful milestone is to run the backend, seed or create lineage records, and verify a real end-to-end lineage graph with live API data.
