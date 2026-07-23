# Self-hosting on a spare laptop (testing phase)

This is the interim hosting plan: run the full stack on a spare
Windows laptop, reachable by you and a handful of testers from
anywhere, without opening any ports on your home router. It's meant
to carry you through early testing until you have real traction - see
"When to graduate" at the end for the signals that mean it's time to
move to AWS or a real server.

Read `docs/13_Roadmap.md` first if you haven't - Phase 1 there
(security review, password reset, rate limiting, etc.) should be
substantially done before real testers put real data into this
instance.

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
git clone https://github.com/<your-org-or-username>/ichnos.git
cd ichnos
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

## 4. Start the stack

```
docker compose up -d --build
```

First build takes a few minutes (installing Python and Node
dependencies). Once it's up:

- Frontend: http://localhost:3000
- Backend health check: http://localhost:8000/ (should return
  `{"status": "running"}`)

Confirm you can register an account and log in before moving on.

## 5. Let testers reach it - Cloudflare Tunnel

Do not forward ports on your router for this. Port forwarding exposes
your home network's public IP directly and is the wrong tool here.
Cloudflare Tunnel opens an outbound-only connection from the laptop to
Cloudflare, so nothing needs to be opened inbound on your router or
Windows Firewall, and you get a real HTTPS URL for free.

**Fastest option - Quick Tunnel (no account needed):**

1. Install `cloudflared`: download the Windows installer from
   [Cloudflare's docs](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/).
2. Run:
   ```
   cloudflared tunnel --url http://localhost:3000
   ```
3. It prints a random URL like `https://random-words.trycloudflare.com`
   - share that with testers. This URL changes every time you restart
   the tunnel, so it's best for short test sessions, not a stable link
   you hand out repeatedly.

**Better option for repeated use - Named Tunnel (needs a free
Cloudflare account and a domain, even a cheap one you buy just for
this):**

1. `cloudflared tunnel login` - opens a browser, log into (or create)
   your Cloudflare account and pick the domain.
2. `cloudflared tunnel create ichnos`
3. Create a config file (e.g. `C:\Users\<you>\.cloudflared\config.yml`):
   ```yaml
   tunnel: ichnos
   credentials-file: C:\Users\<you>\.cloudflared\<tunnel-id>.json
   ingress:
     - hostname: ichnos.yourdomain.com
       service: http://localhost:3000
     - service: http_status:404
   ```
4. `cloudflared tunnel route dns ichnos ichnos.yourdomain.com`
5. Run it as a Windows service so it survives reboots:
   `cloudflared service install`, then `net start cloudflared` (or
   just leave `cloudflared tunnel run ichnos` running in a terminal
   window for casual testing).
6. Testers now reach the app at `https://ichnos.yourdomain.com`.

Either way, once you know the public URL, update `.env`:

```
CORS_ALLOWED_ORIGINS=https://ichnos.yourdomain.com
```

and restart: `docker compose up -d`.

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
  docker exec ichnos_postgres pg_dump -U ichnos ichnos > backup_%date%.sql
  ```
- **Monitoring**: nothing fancy needed yet - a free uptime checker
  (e.g. UptimeRobot) pinging your tunnel URL every few minutes will
  tell you if the laptop or tunnel goes down before a tester does.

## When to graduate off the laptop

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
