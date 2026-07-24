# Security review

Last revised: 2026-07-24. A manual code-level review (not a
penetration test, and not a substitute for one before a real security-
conscious buyer signs a contract) - what it covers, what it found, and
what's still open. Roadmap tracking in `docs/13_Roadmap.md` treats
this document as the Phase 1 "security review" line item.

## What's already solid

- **Tenant isolation**: every query that touches tenant data filters
  by `organization_id`, verified with dedicated cross-org tests
  (`test_auth_tenant_isolation.py` and per-feature tenant-scoping
  tests throughout the suite).
- **Auth**: JWT (HS256) with a required `SECRET_KEY` (the app refuses
  to start without one - no silent insecure default), password
  hashing via `pbkdf2_sha256` (passlib), per-account brute-force
  lockout on `/api/auth/login` after 5 failed attempts in 15 minutes.
- **Secrets at rest**: `DataSource.connection_config` (which can
  contain database passwords) is encrypted with Fernet before
  touching the database - confirmed by a test that reads the raw
  SQLite file bytes and asserts the plaintext password never appears.
- **RBAC**: four roles (admin/steward/data_owner/viewer) enforced via
  a `require_role()` dependency on every mutating endpoint; admin-only
  actions (creating other users) are actually admin-gated, not
  steward-accessible - checked directly in this pass.
- **No SQL injection surface found**: every query in the app goes
  through SQLAlchemy's ORM/query builder with bound parameters; the
  five external-database connectors (Postgres/MySQL/Snowflake/
  Redshift/Azure SQL) read schema metadata through each driver's own
  parameterized introspection calls, not hand-built SQL strings.
- **No code-execution surface found**: no `eval`/`exec`/`pickle`/
  `subprocess`/`os.system` anywhere in the backend.
- **No XSS surface found**: no `dangerouslySetInnerHTML` anywhere in
  the frontend - all rendering goes through React's default escaping.
- **File uploads** (CSV, dbt manifest/catalog JSON) are read in memory
  and parsed directly; the original filename is stored only as
  display metadata, never used to construct a filesystem path - no
  path-traversal surface.
- **CORS**: explicit origin allowlist (`CORS_ALLOWED_ORIGINS`), never
  combined with a wildcard, which the code comments correctly note
  browsers wouldn't honor for credentialed requests anyway.
- **Pinned dependency versions checked against current CVE data**
  (via web search during this review, not from training-data
  recollection): `python-jose==3.5.0` postdates CVE-2024-33663 (fixed
  in 3.3.1); `cryptography==49.0.0` postdates the 46.0.5 floor tied to
  CVE-2026-26007. Nothing pinned in `requirements.txt` matched a
  known-vulnerable range at review time - re-check this periodically
  (`pip list --outdated` / a dependency-scanning CI step - see
  Recommendations) rather than treating this as a one-time result.

## Findings from this pass (fixed during this session)

- **Rate limiter would have collapsed to one shared bucket behind the
  new reverse proxy.** Adding `website/nginx.conf` this session
  (marketing site + app reverse proxy) means the backend's direct TCP
  peer for every request is now the frontend container, not the real
  visitor. The new general API rate limiter (`RateLimitMiddleware`)
  is IP-keyed, so unpatched it would have rate-limited "everyone
  behind the proxy" as a single client - a real user could exhaust
  the whole instance's budget for every other user. Fixed by reading
  `X-Forwarded-For` (set by nginx) ahead of the raw TCP peer, and
  starting uvicorn with `--proxy-headers --forwarded-allow-ips='*'`
  (safe here specifically because the backend is never exposed
  directly to the internet - see `docker-compose.yml`). Covered by
  `test_rate_limiting.py::test_forwarded_for_header_distinguishes_clients_behind_a_proxy`.
  **Caveat**: this assumes Next.js's `rewrites()` proxy (frontend ->
  backend, see `next.config.ts`) passes the incoming `X-Forwarded-For`
  header through unchanged rather than dropping or replacing it. That
  behavior wasn't verified against a running instance in this session
  (no Docker available in this environment) - confirm it once this is
  actually deployed behind the nginx layer, by checking that two
  different real clients get independent rate-limit budgets rather
  than sharing one.

## Open items (not fixed this session - judgment calls for you)

- **No CSRF protection, and none needed.** The frontend authenticates
  with a bearer token in an `Authorization` header (not a cookie), so
  there's no ambient credential for a malicious page to ride on -
  CSRF tokens are a cookie-auth mitigation and don't apply here. Flagging
  only so it doesn't get raised as a gap by someone doing a checklist-
  style review later.
- **Rate limiter is in-memory and per-process.** Fine for the current
  single-laptop, single-process deployment (see `docs/SELF_HOSTING.md`).
  If this ever runs with multiple backend replicas behind a load
  balancer, the limit needs to move to shared storage (Redis, etc.) or
  each replica enforces its own independent budget, effectively
  multiplying the real limit by the replica count.
- **No dependency vulnerability scanning in CI.** This review checked
  a handful of security-sensitive packages by hand; it did not check
  all ~19 backend or all frontend npm dependencies. Recommend adding
  `pip-audit` (backend) and `npm audit` (frontend) as CI steps -
  concrete enough to do in a follow-up pass, not done here to keep
  this review scoped to what could be verified in one sitting.
- **Secrets management is still just a `.env` file** (unchanged from
  the roadmap's existing note) - acceptable for the current
  single-laptop phase per `docs/SELF_HOSTING.md`'s own guidance, but
  a real vault (or at minimum your cloud provider's secrets manager)
  belongs in Phase 3 once this moves off a laptop.
- **No SSO yet** - magic-link passwordless login (shipped this
  session) covers the "no good login recovery path" gap, but an
  actual SSO/SAML option is still Business/Enterprise-tier work per
  the pricing doc, not yet built.
- **Self-hosted source credentials = an admin can reach your internal
  network.** Adding a data source (Postgres, MySQL, etc.) means
  giving the app a hostname/port/credentials to connect to - by
  design, since that's the product. On a self-hosted instance, this
  means any org admin/steward can direct outbound connections to
  arbitrary hosts reachable from wherever the backend runs (an SSRF-
  shaped capability, though it's an *intended*, authenticated feature
  here rather than a bug). Worth being aware of if this backend ever
  runs inside a network segment with sensitive internal services -
  keep it on its own segment, same as you would any tool that takes
  admin-supplied connection strings.

## How to use this document

Treat this as a snapshot, not a certification - re-run a pass like
this (or a real third-party review) before: opening the instance to
external testers with real production data, taking payment from a
first customer, or any time a new inbound connector/integration is
added (each one is new attack surface). The "Open items" list above is
the actual punch list for a follow-up pass; the "already solid"
section is what doesn't need to be re-litigated every time.
