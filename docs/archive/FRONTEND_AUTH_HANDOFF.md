# Frontend Auth Wiring

Date: 2026-07-22
Author: Claude (Cowork), on request from Soumick
Builds on: PHASE0/PHASE1/NEXT_PHASE handoffs (all backend-only until now)

Closes the gap flagged in every prior handoff doc: the backend has
had real auth, multi-tenancy, privacy classification, and an audit
trail since Phase 0, but the Next.js frontend had no login screen and
sent no Authorization header at all - every page would have gotten a
blank/broken screen the moment Phase 0's auth enforcement went live.

## What changed

**`services/api.ts`** - the shared axios instance now:
- attaches `Authorization: Bearer <token>` to every request, reading
  from `localStorage` (key `mip_token`)
- on any `401` response, clears the stored token and redirects to
  `/login`, so an expired/invalid token is handled once, centrally,
  rather than in every page's error handling

**`GET /api/auth/me`** (small backend addition, `api/auth.py`) -
returns the current user's id/email/role plus their organization's
name/slug. Needed because `/api/auth/login` only ever returned a bare
token; the frontend needs somewhere to ask "who am I, and what can I
do" to render the nav bar and gate admin-only UI.

**`contexts/AuthContext.tsx`** - `AuthProvider` + `useAuth()`:
`user`, `loading`, `login()`, `register()`, `logout()`. On mount, if a
token is already in `localStorage`, it's verified against `/api/auth/me`
before any protected page decides whether to redirect - so a page
refresh doesn't flash a login redirect for an already-logged-in user.

**`/login` and `/register` pages** - register collects an
organization name (every signup creates a new org and its first
admin, matching the backend's existing behavior) and immediately logs
in on success rather than showing a second form.

**`hooks/useRequireAuth.ts`** + **`components/TopNav.tsx`** - every
existing protected page (`/`, `/lineage`, `/governance`,
`/datasets/[id]`) now calls `useRequireAuth()` (redirects to `/login`
if not authenticated, once the mount-time check resolves) and renders
`<TopNav />`, which shows the org name, user email, role badge, and a
log-out button. The old per-page "Dashboard" / "Back to Dashboard" /
"View Lineage Graph" links were removed in favor of TopNav's shared
navigation.

**Role-gated UI** - the dashboard hides "Add PostgreSQL Source" and
"Run Scan" for `viewer`-role users (the backend already 403s these for
viewers; this just avoids showing a button that would fail).

## What did NOT change

- No password-reset flow.
- No "invite a teammate to an existing org" flow - still one signup
  per org, matching the backend.
- Token is stored in `localStorage`, not an httpOnly cookie - simplest
  option given the backend has no cookie-setting support, but it's
  worth knowing this is readable by any JS on the page (XSS risk) if
  a stricter security posture becomes a priority pre-launch.
- No loading skeletons / polish beyond a plain "Loading..." state.

## Verification

- `npm run build` (Next.js production build, which also runs the
  TypeScript compiler) succeeds with all 7 routes present, including
  the two new ones:
  ```
  ┌ ○ /
  ├ ○ /_not-found
  ├ ƒ /datasets/[id]
  ├ ○ /governance
  ├ ○ /lineage
  ├ ○ /login
  └ ○ /register
  ```
- `npm run lint` passes with zero errors (one real issue was caught
  and fixed along the way: an eslint-plugin-react-hooks rule flagging
  a setState call reachable from inside a `useEffect` via a
  `useCallback`-memoized function - fixed by moving the mount-time
  token-verification logic to a plain function declared directly
  inside the effect, which is the same shape the app's other
  pre-existing data-fetching effects already use).
- Backend: added `test_me_returns_current_user_and_org` /
  `test_me_requires_auth` for the new endpoint; full suite is
  41/41 passing.

## How to run this locally

```bash
# backend (see PHASE0_HANDOFF.md for full .env setup)
cd backend && uvicorn app.main:app --reload

# frontend
cd frontend
npm install
npm run dev
```

Visit `http://localhost:3000/register` to create the first
organization and admin user, then you'll land on the dashboard with a
real session - Phase 0's auth enforcement, Phase 1's privacy
classification, and the audit trail/privacy dashboard from the "Next"
phase are all now reachable end-to-end, not just via the API.

## Delivery note

Same as prior phases - no push access to the GitHub repo from this
environment. `frontend-auth-wiring.patch` applies on top of a
checkout with all prior phases applied.
`metadata-platform-all-phases.zip` (re-attached) now includes this
work too if you'd rather copy `backend/` and `frontend/` wholesale.
