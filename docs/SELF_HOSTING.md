# Self-hosting (interim plan)

This is the interim hosting plan, in two phases on two different
machines:

- **Phase A - now:** run the full stack on the same laptop you're
  developing on. Nobody outside you touches it yet, so there's no
  tunnel or public URL needed - `http://localhost` (marketing site)
  and `http://app.localhost` (the app) are enough.
- **Phase B - once you're ready for outside testers:** move to a
  second, dedicated laptop (doesn't need to be powerful - see
  hardware notes below) that stays on and reachable at all times,
  independent of whatever you're doing on your main machine. That's
  when the Cloudflare Tunnel setup in step 5 comes in.

Both phases use the exact same `docker-compose.yml` - moving from A to
B is "clone the repo onto the second laptop and start it there," not a
rebuild. See "When to graduate off the laptop(s) entirely" at the end
for the signals that mean it's time to move to AWS or a real server
instead of a second laptop.

Read `docs/13_Roadmap.md` first if you haven't - Phase 1 there
(security review, passwordless login, rate limiting, etc.) should be
substantially done before real testers put real data into this
instance. That's the gate for moving from Phase A to Phase B here, not
a hard prerequisite for running this on your own machine today.

## 1. Prepare the laptop

1. Windows 11 (or Windows 10 2004+) with virtualization enabled in
   BIOS.
2. Install WSL2: open PowerShell as Administrator and run
   `wsl --install`, then reboot.
3. Install [Docker Desktop for Windows](https://www.docker.com/products/docker-desktop/)
   and make sure it's set to use the WSL2 backend (Settings ->
   General -> "Use the WSL 2 based engine").
4. Settings that matter for an always-on box:
   - Power & sleep settings -> set "Sleep" to Never while plugged in.
   - Keep the laptop on AC power, lid open (or set "when I close the
     lid: do nothing" under Power Options, if you want to close it).
   - Windows Update -> keep automatic updates on, but be aware
     updates can trigger a reboot; see the backup/restart notes below.

## 2. Get the code onto the laptop

Once the GitHub repo exists (see the git/CI setup you already have),
clone it:

```
git clone https://github.com/<your-org-or-username>/datafe.git
cd datafe
```

## 3. Configure secrets

```
copy .env.example .env
```

Edit `.env` and fill in real values - do not ship the placeholders:

- `POSTGRES_PASSWORD` - any strong password.
- `SECRET_KEY` - generate with
  `python3 -c "import secrets; print(secrets.token_urlsafe(48))"`
  (Docker Desktop ships a Linux VM, so you can also just run this
  inside any Python container, or use an online UUID/token generator
  as a fallback for a one-off value).
- `ENCRYPTION_KEY` - generate with
  `python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`.
  **Back this up somewhere outside the laptop** (a password manager
  is fine) - if the laptop's disk is lost, every stored data-source
  credential becomes unrecoverable without it.
- `CORS_ALLOWED_ORIGINS` - leave as `http://localhost:3000` for now;
  you'll update this once you have your tunnel URL in step 5.
- `GITHUB_CLIENT_ID` / `GITHUB_CLIENT_SECRET` - optional, enables the
  "Continue with GitHub" button on the login page. Register a free
  OAuth App at https://github.com/settings/developers -> "New OAuth
  App" (no credit card required, unlike Google's OAuth consent
  screen). Set:
  - Homepage URL: your `FRONTEND_URL` value (e.g. `http://app.localhost`)
  - Authorization callback URL: `<FRONTEND_URL>/login/github/callback`
    (e.g. `http://app.localhost/login/github/callback`)

  Copy the generated Client ID, and a generated Client Secret, into
  `.env`. **Revisit this once you reach step 5** - the callback URL
  has to match whatever `FRONTEND_URL` ends up being for your tunnel,
  so you'll need to update the GitHub OAuth App's callback URL (and
  re-save `.env`'s `GITHUB_CLIENT_ID`/`SECRET` if you registered a
  fresh app rather than editing the existing one) once outside
  testers are involved. Leave both blank to skip this - the button
  still shows but returns a clear "not configured" error instead.

## 4. Start the stack

```
docker compose up -d --build
```

First build takes a few minutes (installing Python and Node
dependencies). Once it's up:

- Marketing site: http://localhost
- App: http://app.localhost (most modern browsers resolve
  `*.localhost` to `127.0.0.1` automatically, no `/etc/hosts` edit
  needed - if yours doesn't, http://localhost:3000 reaches the app
  container directly as a fallback)
- Backend health check: http://localhost:8000/ (should return
  `{"status": "running"}`)

Confirm you can register an account and log in before moving on. This
much - Phase A - is everything you need while it's just you.

## 5. Phase B: let outside testers reach it - Cloudflare Tunnel

This is the point where you move to the **second laptop** - a
dedicated, always-on machine, separate from whatever you're doing your
own work on day to day. It doesn't need to be powerful; anything that
can run Docker Desktop and stay on comfortably is enough. Repeat steps
1-4 above on that machine, then continue here.

Do not forward ports on your router for this. Port forwarding exposes
your home network's public IP directly and is the wrong tool here.
Cloudflare Tunnel opens an outbound-only connection from the laptop to
Cloudflare, so nothing needs to be opened inbound on your router or
Windows Firewall, and you get real HTTPS URLs for free.

**Fastest option - Quick Tunnel (no account needed, one hostname
only):**

1. Install `cloudflared`: download the Windows installer from
   [Cloudflare's docs](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/).
2. Run:
   ```
   cloudflared tunnel --url http://localhost:80
   ```
3. It prints a random URL like `https://random-words.trycloudflare.com`
   - that single URL serves the marketing site at `/`. Quick Tunnels
   only expose one hostname, so this option can't also give you a
   separate `app.` URL - use it for a quick look at the marketing
   site, not for testers who need to log into the app. Use the Named
   Tunnel option below for real testing.

**Named Tunnel (needs a free Cloudflare account and a domain) - gives
you both hostnames. The domain is `datafetech.com`, registered and
managed through Cloudflare:**

1. `cloudflared tunnel login` - opens a browser, log into your
   Cloudflare account and pick `datafetech.com` when prompted.
2. `cloudflared tunnel create datafe`
3. Create a config file (e.g. `C:\Users\<you>\.cloudflared\config.yml`).
   Both hostnames point at the same local port - the `website`
   container (nginx) reads the `Host` header and routes the marketing
   site vs. the app accordingly:
   ```yaml
   tunnel: datafe
   credentials-file: C:\Users\<you>\.cloudflared\<tunnel-id>.json
   ingress:
     - hostname: datafetech.com
       service: http://localhost:80
     - hostname: app.datafetech.com
       service: http://localhost:80
     - service: http_status:404
   ```
4. `cloudflared tunnel route dns datafe datafetech.com` and
   `cloudflared tunnel route dns datafe app.datafetech.com` - this
   creates the CNAME records in the `datafetech.com` zone pointing at
   the tunnel automatically; nothing to add by hand in the Cloudflare
   DNS dashboard.
5. Run it as a Windows service so it survives reboots:
   `cloudflared service install`, then `net start cloudflared` (or
   just leave `cloudflared tunnel run datafe` running in a terminal
   window for casual testing).
6. Testers now see the marketing site at `https://datafetech.com` and
   reach the app at `https://app.datafetech.com`.

Either way, once you know the app's public hostname, update `.env`:

```
CORS_ALLOWED_ORIGINS=https://app.datafetech.com,https://datafetech.com
FRONTEND_URL=https://app.datafetech.com
```

`FRONTEND_URL` matters here too, not just `CORS_ALLOWED_ORIGINS` - it's
what builds the link in magic-link login emails, and (if you set up
GitHub OAuth in step 3) the GitHub callback URL. If you leave it on
`http://app.localhost` after moving to a real tunnel hostname, both of
those break silently for anyone outside your own machine.

If you configured GitHub OAuth, also go back to the OAuth App at
https://github.com/settings/developers and update its Authorization
callback URL to `<new FRONTEND_URL>/login/github/callback`.

Then restart: `docker compose up -d`.

## 6. Keep it running

- **Auto-start on boot**: Docker Desktop has a setting to start on
  login (Settings -> General -> "Start Docker Desktop when you log
  in"). Combine with Windows' auto-login (or just leave the machine
  logged in) so a power blip or Windows Update reboot recovers on its
  own. `docker compose`'s `restart: unless-stopped` (already set in
  `docker-compose.yml`) means containers come back up once Docker
  Desktop itself is running again.
- **Backups**: this is the single biggest risk of laptop hosting -
  one bad Windows Update, spilled coffee, or disk failure and
  everything is gone. At minimum, schedule a nightly `pg_dump` via
  Windows Task Scheduler and copy the dump somewhere off the laptop
  (a cloud storage folder, an external drive, anywhere else). Example
  dump command:
  ```
  docker exec datafe_postgres pg_dump -U datafe datafe > backup_%date%.sql
  ```
- **Monitoring**: nothing fancy needed yet - a free uptime checker
  (e.g. UptimeRobot) pinging your tunnel URL every few minutes will
  tell you if the laptop or tunnel goes down before a tester does.

## When to graduate off the laptop(s) entirely

Move to AWS (or any real hosting) when any of these becomes true:

- You have paying customers, or anyone depending on uptime you can't
  personally guarantee (a laptop reboots for Windows Updates whether
  you planned for it or not).
- You need the app reachable reliably while the laptop is closed,
  asleep, or off your home network.
- A prospective customer's security review asks where their data is
  hosted, and "a laptop in my apartment" is a blocker (it will be, for
  most B2B buyers, even small ones).
- Data volume or concurrent usage starts to strain a single machine.
- You want redundancy - a laptop is a single point of failure with no
  failover.

At that point, the Docker images and `docker-compose.yml` you already
have translate directly: the same containers run on an EC2 instance,
ECS, or a managed Postgres (RDS) with only environment-variable
changes - no rewrite needed.
