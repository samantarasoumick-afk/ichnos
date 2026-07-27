# CI/CD and environments

Two branches, two purposes:

- **`main`** - active development. Every push and PR runs the full CI
  suite (backend pytest, frontend typecheck/lint/build). This is
  where day-to-day work happens - treat it as "should always be
  reasonably stable," not "never broken for five minutes."
- **`production`** - what's actually deployed at `datafetech.com` /
  `app.datafetech.com`. Only ever moves forward by merging `main` into
  it, deliberately, when you're ready to ship what's currently on
  `main`. A push to `production` triggers CI and then, if it's green,
  an automatic deploy - see below.

Nothing pushes directly to `production` day to day. The promotion
step is always "merge main into production," never new commits
authored on production itself.

## Environments

Two running copies of the app exist, and they should stay
deliberately different in a few ways:

| | Dev (your Mac, day to day) | Production (`datafetech.com`) |
|---|---|---|
| Branch | `main` | `production` |
| `.env` `FRONTEND_URL` | `http://app.localhost` | `https://app.datafetech.com` |
| `.env` `CORS_ALLOWED_ORIGINS` | `http://app.localhost,http://localhost` | `https://app.datafetech.com,https://datafetech.com` |
| Stripe keys | test-mode keys (or blank) | live keys |
| `DEMO_SEED` | fine to leave `false`; use the in-app Demo Data panel instead | `false` - never seed synthetic data into a real instance |
| `AUTO_CREATE_SCHEMA` | `false` - migrations are the source of truth in both | `false` |

The two `.env` files are separate, gitignored, and never copied
wholesale between machines - only specific values (like a rotated
`SECRET_KEY`) move between them deliberately, by hand.

## Deploying (promotion checklist)

1. Confirm CI is green on `main` (GitHub → Actions tab, or just look
   for the green check next to the latest commit).
2. Open a PR from `main` into `production` (or merge directly if
   you're comfortable skipping the PR review step for now - either
   works, a PR just gives you a diff to eyeball before it ships).
3. Merge it. This push to `production` triggers CI again, and if both
   check jobs pass, the `deploy` job runs automatically on the
   production host (see runner setup below) - `docker compose up -d
   --build`. No manual SSH/RDP step needed once this is set up.
4. Watch the Actions tab for the `deploy` job to go green (a few
   minutes - it's rebuilding Docker images).
5. Spot-check `https://datafetech.com` and `https://app.datafetech.com`
   - confirm the change you expected actually shows up, and that
   login/register still works.

If the `deploy` job never appears / stays queued forever, the
self-hosted runner isn't running - see below.

## Self-hosted runner setup (one-time, on the production host)

GitHub Actions' cloud runners can't reach a machine sitting behind a
home network - there's no public IP or SSH access to deploy to
"normally." A **self-hosted runner** solves this the opposite way: a
small agent process runs on the production machine itself and polls
GitHub for jobs, so no inbound connection is ever needed - the same
outbound-only model as the Cloudflare Tunnel already in use.

On the production host (whichever machine is actually serving
`datafetech.com` - see `docs/SELF_HOSTING.md` for how that's chosen):

1. GitHub repo → **Settings → Actions → Runners → New self-hosted
   runner**. Pick the OS shown (macOS or Windows, matching the
   production host).
2. Follow the exact download/configure commands GitHub generates on
   that page - they include a one-time registration token, so copy
   them fresh from the page rather than reusing old commands from
   elsewhere. When prompted for labels during `./config.sh` (or
   `config.cmd` on Windows), add the label `production` (in addition
   to the defaults) - the deploy job in `.github/workflows/ci.yml`
   specifically targets `[self-hosted, production]`, so the label has
   to match exactly.
3. Run it as a persistent service rather than a one-off foreground
   process, so it survives reboots the same way `cloudflared` and
   Docker Desktop do:
   - macOS: `./svc.sh install && ./svc.sh start` (from inside the
     runner's install directory).
   - Windows: the runner's own setup script offers to install itself
     as a Windows service - accept that prompt.
4. Confirm it shows **Idle** (green) on the Settings → Actions →
   Runners page - that means it's polling and ready.
5. Make sure a real `.env` file already exists in the runner's working
   directory for this repo (typically
   `actions-runner/_work/ichnos/ichnos/.env` on macOS, or the
   equivalent path on Windows) before the first deploy runs - it won't
   be there automatically (`.env` is gitignored, so `git`/`checkout`
   never creates it). Copy your existing production `.env` there once;
   after that it persists across deploys since the checkout step is
   configured with `clean: false`.

From this point on, merging `main` into `production` is the entire
deploy process - no manual `git pull` / `docker compose up --build` on
the host required, though those commands still work fine as a manual
fallback if the runner is ever down.

## Why not just deploy from GitHub's cloud runners directly?

Because there's nothing to deploy *to* from the cloud - the app runs
on a laptop with no public inbound access by design (see
`docs/SELF_HOSTING.md`'s reasoning against port-forwarding). A
self-hosted runner is the standard way GitHub Actions supports this
exact shape of setup, and it's what to swap out - not the branch
strategy above - if this ever graduates off a laptop onto real
infrastructure (EC2, etc.), per the "graduate off the laptop" section
in `docs/SELF_HOSTING.md`.
