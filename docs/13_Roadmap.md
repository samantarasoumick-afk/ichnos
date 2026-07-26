# Roadmap

Last revised: 2026-07-26. Everything under "Delivered" is built and
covered by the backend test suite (371 passing tests as of this
revision) and the frontend's own Jest suite (47 tests) plus
typecheck/lint. Everything under Phases 1-3 is
what stands between here and a real rollout - see the verdict at the
end for how to read this list.

## Delivered

**Discovery & catalog** - source registration and scanning for
Postgres, MySQL, Snowflake, Redshift, S3, Azure SQL/Synapse, dbt
artifact upload, Tableau Metadata API, Stripe (the first SaaS-of-
record connector, sampling Customer/Charge/Invoice/Subscription
objects rather than a SQL schema), and CSV upload; AI-generated
dataset summaries; column-level metadata (description, sample values,
classification); auto data classification (Master/Reference/
Transactional/Analytical); System of Record / System of Reference
tagging.

**Lineage** - automatic FK-based discovery plus manually-documented
edges (transformation type, description, filter logic); a
lineage-adjusted data quality score that rewards well-documented
transformations; full-graph and dataset-scoped lineage views.

**Data quality** - real profiling from scan-time statistics
(completeness, uniqueness, validity, consistency, freshness), not
simulated; surfaced per-dataset and blended with lineage inheritance;
a catalog-wide Data Quality page, sorted worst-first with domain/
threshold filters, so problem datasets surface without opening each
one individually.

**Governance** - business glossary with dataset/column-level linking;
business process repository, now with a plain-language "narrative"
field per process (e.g. "A Customer (Master) orders (Transactional)
from a Store (Master) in Mumbai (Reference)") and datasets grouped by
Master/Reference/Transactional/Analytical classification when viewing
a process; linking a dataset to a process auto-creates or reuses a
glossary term for it, so the glossary builds itself as processes get
modeled instead of being maintained as a wholly separate exercise;
data contracts (schema-level + breach logging); certification
request/approval workflow; governance maturity score with
recommendations; audit log with filtering and CSV export; governance
discussion threads (Question / Proposal / Issue, the last with
stakeholder follow-through); a risk register (likelihood x impact
scoring, linked to datasets and processes) and a reusable control
library, with risk coverage feeding into the maturity score as its
own dimension.

**Privacy** - DPDP/GDPR-oriented sensitivity classification, purpose
mapping, consent tracking, retention policy enforcement, privacy
dashboard, compliance report export.

**Platform** - multi-tenant org isolation on every query; RBAC
(admin, steward, data_owner, viewer); JWT auth (password, magic-link,
and GitHub OAuth) with login lockout; credentials encrypted at rest;
a global cross-entity search bar in the top nav (datasets, glossary
terms, processes, risks, controls, and discussion threads, ranked by
the same local TF-IDF retrieval the NL Q&A assistant uses - no
external API call), plus an "@" mention picker on both the search bar
and the Ask page for referencing a specific entity by exact name
instead of relying on keyword matching; every Ask question and search
query is logged with a matched/unmatched signal, rolling up into an
admin-only "Search Insights" report (top unanswered questions ranked
by frequency, plus overall query volume) so recurring gaps become
visible candidates for a new built-in intent or glossary entry; NL Q&A
assistant over the catalog - LLM-backed
(Anthropic) open-ended, multi-turn answers grounded in real
catalog/DQ/lineage data when `ANTHROPIC_API_KEY` is set, falling back
to deterministic keyword-matched intents + TF-IDF semantic retrieval
otherwise; team management.

## Rollout-readiness verdict

The product surface area above is strong for the target segment -
stronger than most seed-stage catalog tools at this point. What's
missing isn't features, it's the operational and trust scaffolding
that makes a governance product safe to hand to someone else's data.
The phases below are sequenced by blast radius: Phase 1 has to happen
before any external user or real data touches an instance, Phase 2
before charging money, Phase 3 before scaling past a handful of
customers.

## Phase 1: Trust & operational baseline (before any external user)

- [x] Git version control + CI (backend pytest, frontend typecheck/
      lint/build on every push and PR)
- [x] Dockerized backend + frontend, docker-compose for self-hosting
- [x] Independent security review of the codebase - see
      `docs/SECURITY_REVIEW.md`; open items from it are tracked there,
      not duplicated here
- [x] Passwordless "magic link" login, doubling as the password-
      recovery path (there's no separate reset-token flow - a user who
      can receive mail at their account address can always get back
      in). Covers the practical gap the old "admin sets a password
      directly" flow left open.
- [x] A true SSO option: "Sign in with GitHub" (`GET
      /api/auth/oauth/github/start` + `POST
      /api/auth/oauth/github/callback`, `app/services/oauth_service.py`).
      Google OAuth was the original plan but its consent-screen
      verification requires billing/card details on the Google Cloud
      account; GitHub's OAuth App registration is free with no card
      needed, and is arguably the better first provider anyway given
      DataFe's early users. Links to an existing password/magic-link
      account by email, or creates a new user + org for a first-time
      sign-in - same as password registration does. Real SAML for
      larger enterprise buyers is still open.
- [x] General API rate limiting (`app/middleware/rate_limit.py`) -
      IP-keyed (X-Forwarded-For-aware, so it survives sitting behind
      the website's nginx reverse proxy), on top of the existing
      per-account login lockout
- [ ] Secrets management beyond a `.env` file once this leaves a
      single laptop (a proper vault or cloud secrets manager)
- [ ] Error tracking (e.g. Sentry) - needs a Sentry account/DSN from
      you before it can be wired up, not done this pass
- [x] A real `/health` endpoint (now checks actual DB connectivity,
      not just "the process is up") and structured JSON logging with
      a request ID on every log line, tying a user-reported error back
      to the exact log lines it produced

## Phase 2: Product completion (before charging money)

- [ ] Billing/subscription enforcement - the pricing strategy doc
      (`docs/DataFe_Pricing_Strategy.docx`) describes tiers, but
      nothing in the app meters or enforces them yet
- [x] Masking capability for sensitive columns - Data Owner/admin can
      mask a column's sample values from Viewers; classification now
      leads to an actual control, not just a label
- [x] Data contract enforcement beyond logging: DQ threshold checks
      (a contract can require a minimum quality score) and lineage
      breach propagation (a downstream dataset surfaces any breached
      upstream contract reachable via lineage)
- [x] Genuine role-based landing experiences - Data Owner sees a
      pending-approval queue, Steward sees a stewardship-gaps queue,
      Viewer gets a lighter page; admin sees both queues
- [x] A connector matching a typical small company's real stack:
      Stripe (SaaS-of-record, not warehouse-native) - Salesforce/
      HubSpot/QuickBooks remain open, tracked in the backlog
- [ ] Frontend automated test coverage (Jest/Playwright) - today only
      the backend has tests, so UI regressions can ship silently
- [x] Terms of Service, DPA, and Privacy Policy - live at /terms.html,
      /dpa.html, /privacy.html, explicitly flagged as early-access
      drafts pending real legal review

## Phase 3: Scale (before growing past a handful of customers)

- [ ] SOC 2 preparation (increasingly a hard requirement even for SMB
      buyers evaluating a governance tool)
- [ ] Move off a self-hosted laptop onto real infrastructure (see
      `docs/SELF_HOSTING.md` for the interim setup and the signals
      that mean it's time to graduate)
- [ ] Governance maturity trend snapshots + dashboard (currently a
      point-in-time score only)
- [ ] Broader connector coverage (generic OpenAPI/Swagger importer,
      more SaaS + warehouse sources, website consent/tracking
      inventory)
- [ ] Steward assignment/triage queue and contract-approval workflow
- [ ] Broader role model redesign as real usage surfaces gaps in the
      current four roles

## How to use this list

Phase 1 is the only phase that's non-negotiable before letting anyone
outside your own machine log in with real data. Phase 2 is what
separates a demo from something you can charge for. Phase 3 is what
you'll feel the absence of once you have real usage, not before -
don't front-load it.
