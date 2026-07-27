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

| | Dev (your Mac, day to day) | Production (Windows laptop, `datafetech.com`) |
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

## Self-hosted runner setup (one-time, on the Windows laptop)

GitHub Actions' cloud runners can't reach a machine sitting behind a
home network - there's no public IP or SSH access to deploy to
"normally." A **self-hosted runner** solves this the opposite way: a
small agent process runs on the production machine itself and polls
GitHub for jobs, so no inbound connection is ever needed - the same
outbound-only model as the Cloudflare Tunnel already in use.

Production is the Windows laptop running `cloudflared` and the
`docker compose` stack behind `datafetech.com`. Set the runner up
there, in PowerShell:

1. GitHub repo → **Settings → Actions → Runners → New self-hosted
   runner** → select **Windows**.
2. Copy and run the exact download/configure commands the page
   generates - they include a one-time registration token, so use the
   fresh commands from that page rather than reusing these. They'll
   look like:
   ```powershell
   mkdir actions-runner ; cd actions-runner
   Invoke-WebRequest -Uri <url-from-the-page> -OutFile actions-runner-win-x64.zip
   Expand-Archive -Path actions-runner-win-x64.zip -DestinationPath $PWD
   ./config.cmd --url https://github.com/samantarasoumick-afk/ichnos --token <token-from-the-page>
   ```
3. When `config.cmd` prompts for runner labels, add `production` in
   addition to the defaults it suggests - the deploy job in
   `.github/workflows/ci.yml` specifically targets
   `[self-hosted, production]`, so the label has to match exactly. It
   will also ask which folder to run jobs in - the default (inside
   the `actions-runner` folder itself) is fine.
4. Install it as a Windows service so it survives reboots the same
   way Docker Desktop and `cloudflared` do, rather than needing a
   terminal window left open:
   ```powershell
   ./svc.cmd install
   ./svc.cmd start
   ```
5. Confirm it shows **Idle** (green) on the Settings → Actions →
   Runners page - that means it's polling and ready.
6. Before the first deploy runs, copy your real production `.env`
   file into the runner's checkout folder for this repo - typically
   `actions-runner\_work\ichnos\ichnos\.env`. It won't be there
   automatically (`.env` is gitignored, so `checkout` never creates
   it), and it only needs doing once - after that it persists across
   deploys since the checkout step is configured with `clean: false`.
   This becomes the new canonical clone the deploy step builds from;
   your existing manually-cloned folder is no longer what's actually
   serving `datafetech.com` once this is set up, so treat this
   `actions-runner\_work\ichnos\ichnos` folder as production from here
   on (or point `docker compose` commands you run by hand at it too,
   to avoid two folders drifting apart).

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
