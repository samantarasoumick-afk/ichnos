# 17. AI Context Store Strategy

## The thesis

Foundation model companies have spent enormous effort embedding the world's public reference data — the outside layer. Every company sitting on years of internal operational data has a second layer that no foundation model has or ever will have by default: the proprietary, contextual knowledge of how *this* business actually works — what a term means here, who owns what, what's upstream of what, what's currently broken, what's regulated, what's certified. AI strategy inside a company only becomes reliable and scalable once these two layers are reconciled — the model's general capability grounded in the company's specific reality — and that reconciliation has to be structured and repeatable (deterministic), not a fresh ad hoc RAG stuffing exercise every time someone builds a new AI feature.

DatFe is already, without having been positioned this way, building the internal-context half of that equation: a governed catalog (datasets, columns, lineage), a business glossary, ownership and stewardship, data contracts with real enforcement, quality and freshness scoring, PII/DPDP classification, a risk and control register, and — critically — an existing retrieval layer (TF-IDF fallback + Voyage AI embeddings) feeding an LLM-backed Ask assistant that already refuses to answer beyond what the catalog actually contains. `docs/10_AI_Metadata.md`'s stated direction — "AI enrichment should remain explainable and grounded in catalog facts" — is the same thesis in miniature. This document extends that direction into three concrete build directions: an MCP context server, a metrics/semantic layer, and an external-reference reconciliation layer, in that order of buildability.

## Where DatFe already stands (as of this doc)

Grounding this in what actually exists today, not aspiration:

- **Structured catalog as source of truth.** Datasets, columns, lineage (dataset- and column-level), business processes, glossary terms, data contracts, risks/controls all live in governed Postgres tables — not a vector store. This matters more than it sounds like it should (see the metrics-layer section below): a catalog built on structured, queryable, versioned rows is the right foundation for determinism in a way a vector-DB-first design isn't.
- **A real retrieval layer already exists.** `catalog_search_service.build_corpus()` / `semantic_search()` cover seven doc types today — `dataset`, `column`, `glossary_term`, `process`, `risk`, `control`, `discussion_thread` — with `embedding_service.py` as a Voyage AI-backed upgrade that degrades to the TF-IDF path automatically (no key configured, network failure, empty query — anything goes wrong, it falls back silently, never breaks the caller).
- **A real grounded-LLM assistant already exists.** `assistant_service.py` calls Claude directly (raw HTTP, `claude-sonnet-5` by default) with a system prompt that explicitly forbids inventing facts not in the retrieved context, and has a full non-LLM fallback path (keyword intent detection + template answers) for orgs that haven't configured `ANTHROPIC_API_KEY`. This is, in miniature, exactly the "cross-fit internal context with model capability" pattern the thesis describes — it's just built as a human-facing chat feature today, not as infrastructure other systems can consume.
- **A real trust/provenance envelope already exists.** Every dataset already carries governance_status, certification, contract_status, freshness_status, quality_score — computed, not asserted. This is the part most RAG-over-a-wiki systems don't have: context that comes with a machine-readable answer to "should I trust this."
- **Precedent for external reconciliation already exists, narrowly.** `privacy_engine.py`'s `dpdp_category` classification (`contact`, `government_id`, `financial`, `health`, `biometric`, `sensitive_personal`, `identity`, `credentials`) is literally an internal-column-to-external-regulatory-taxonomy mapping. It's the smallest possible working example of direction 3, already shipped, just not generalized or framed that way yet.
- **The explicit gap.** There is currently zero notion of a computed/derived value anywhere in the platform — no `formula`, `sql_expression`, or metric-definition concept in the glossary or anywhere else. `BusinessGlossaryTerm` is `term` + `definition` (prose) + `domain` + `owner`, linked to datasets/columns via `GlossaryTermLink`. It documents meaning; it does not define how to compute anything. That's the exact gap direction 2 fills.

---

## Direction 1: MCP context server

### Why this first

It's the smallest lift of the three because it wraps infrastructure that already exists, and it's the one that converts "DatFe has good internal context" into "DatFe is a context source any AI agent can plug into" — which is the whole point of the thesis. Today, an agent (Claude Desktop, Claude Code, an internal copilot, a customer's own agent stack) has no standard way to ask DatFe anything. `/api/assistant` is shaped for a chat UI turn, not for tool-calling. MCP is the industry-standard shape for exactly this gap.

### What it looks like concretely

A new MCP server process (or an MCP-compatible route mounted alongside the existing FastAPI app) exposing a small number of **tools**, each backed by a function that already exists:

- `search_catalog(query, doc_types?)` → wraps `embedding_service.semantic_search()` (falls back to `catalog_search_service.semantic_search()` automatically, already handled). Returns `describe_document()`'s (subtitle, url) shape plus the raw snippet.
- `get_dataset_context(schema_name, table_name)` → returns the full trust envelope for one dataset: owner, steward, domain, certification, governance_status/score, quality_score, freshness_status, contract_status, PII/DPDP summary — everything already computed and sitting on the `Dataset` row and its `DatasetResponse` schema. No new computation, just a new shape of exposure.
- `trace_lineage(dataset, direction)` → wraps the existing dashboard-trace/lineage services (`dashboard_trace_service.py`, `ecosystem_service.dataset_tier()`), giving an agent "what feeds this, what depends on this" in one call instead of it trying to infer pipeline structure from table names.
- `get_glossary_term(term)` → resolves a business term to its `definition`, `domain`, `owner`, and every dataset/column it's linked to via `GlossaryTermLink` — this is the tool that lets a model stop guessing what "churn" or "MRR" means in *this* company and instead retrieve the governed answer.
- `get_contract_status(dataset)` → surfaces `last_status`, `last_breach_details`, `activated_by_email`/`activated_at`, and any upstream breaches (`get_upstream_contract_breaches()` already exists) — so an agent reasoning over a dataset can see "this is currently breached, don't treat it as reliable" before it ever gets to generating an answer, not after.

Every tool response should carry the trust envelope fields (governance_status, contract_status, freshness) inline, not as a separate call — that's the differentiator: an agent using DatFe as context gets provenance for free, by construction, rather than having to remember to ask for it.

### Scope discipline for v1

Read-only. No tool should let an agent mutate the catalog in v1 — that's a meaningfully bigger trust and audit surface (who's accountable for a change an agent made vs. a human), and it's not needed to prove the thesis. `log_audit_event()` should still fire on every MCP tool call (`resource_type="mcp_tool_call"` or similar), the same audit-log pattern already used everywhere else in the codebase, so "which agent asked what, when" is visible to a steward from day one.

### Multi-tenancy and auth

Every existing API route is already org-scoped off the authenticated user's `organization_id`. An MCP server needs its own credential model — almost certainly a long-lived, org-scoped API key (not a user's JWT, since an agent session isn't a browser session) that resolves to an organization the same way `get_current_user` resolves a JWT today. This is new plumbing, but small: one new `ApiKey` model + one new auth dependency, not a rearchitecture.

### Relationship to the existing Ask assistant

Ask stays the human-facing chat surface. The MCP server is the agent-facing sibling exposing the same underlying retrieval and trust data as composable tools instead of one chat completion. They should share the exact same `catalog_search_service`/`embedding_service` functions — no forked retrieval logic, or the two surfaces will silently drift in what they consider "the answer."

### Rough phasing

**v1** (days, not weeks, given how much already exists): `search_catalog`, `get_dataset_context`, `get_glossary_term`, `get_contract_status` — all read-only, org-scoped API key auth, audit-logged. **v2**: `trace_lineage`, plus a `describe_column` tool exposing PII/DPDP classification per column (this alone is a strong pitch to any org doing AI-on-their-own-data work who needs to know what's safe to hand to a model). **v3**, only after real usage signal: narrowly-scoped write tools (e.g., an agent flagging a suspected stewardship gap for human review — never an agent silently changing governance state).

---

## Direction 2: Metrics / semantic layer

### The gap this closes

A glossary term today is a paragraph. It tells a human (or a model reading it) what "customer lifetime value" *means*, but not how to *compute* it, and there's nothing stopping five different dashboards, five different analysts, and now potentially five different AI agents from each recomputing it slightly differently. That's the opposite of the "deterministic" requirement in the original thesis — prose grounding reduces hallucination about *meaning*, but does nothing for consistency of *value*. This is genuinely new territory for the codebase, not an extension of something that exists.

### An important scope decision: registry, not execution engine

The tempting design is to make DatFe run the query and hand back a number. Resist that — it would turn a metadata/governance platform into a live query engine against every connected warehouse, a materially different (and materially riskier — arbitrary query execution against customer databases) product than what DatFe is today, and one that duplicates what dbt's Semantic Layer, Cube, LookML, and the customer's own BI tool already do well. The more consistent, more defensible position: **DatFe becomes the governed registry and single source of truth for the metric's *definition*** — the formula, its owner, its version history, its dependency graph, its enforcement state — while *execution* is delegated to whatever already has query access (the warehouse, the BI tool, or an agent that's separately been granted query credentials). DatFe's job is making sure that whoever executes it is executing the one true, versioned, owned definition — not inventing scope creep into becoming a query engine.

### Concrete data model sketch

A new `MetricDefinition` model, deliberately shaped like a cross between `BusinessGlossaryTerm` (definitional metadata) and `DataContract` (versioning + enforcement):

- `term` / `definition` — same as glossary, kept so this can literally supersede or link to an existing `BusinessGlossaryTerm` rather than forcing a second, disconnected naming system.
- `sql_expression` (or a structured aggregation recipe: source table, aggregation function, filter, grain) — the actual, single, governed computation.
- `grain` — the level at which this is valid (per-customer, per-day, org-wide) — metrics silently misused at the wrong grain are one of the most common sources of "the AI gave a plausible-sounding wrong number."
- `unit` — currency, percentage, count, ratio — small field, large hallucination-prevention value (a model that doesn't know MRR is in cents vs. dollars will confidently state the wrong magnitude).
- `owner`, `version`, `status` (DRAFT/ACTIVE/DEPRECATED — reuse the exact lifecycle `DataContract` already has, including a version history rather than in-place mutation of an ACTIVE definition).
- `dataset_dependencies` — which datasets/columns this reads from, expressed the same way `GlossaryTermLink` already links a term to datasets/columns, so the existing lineage graph and Ecosystem View can show "this metric depends on these tables" for free, and a schema change upstream can be flagged against every metric that depends on it the same way `get_upstream_contract_breaches()` already flags dependent datasets today.
- `last_validated_at` / `last_validation_status` — mirroring `DataContract.last_evaluated_at`/`last_status`: periodically (or on-demand) re-run the expression against the current schema shape (not necessarily the full query — even just "do these referenced columns still exist, with compatible types" is most of contract enforcement's actual value) and flag drift the same way a breached contract is flagged today.

### How this plugs into direction 1

`get_metric_definition(name)` becomes an MCP tool with the same shape as `get_glossary_term`, except it returns something an agent (or a downstream BI/semantic-layer tool) can actually execute deterministically, plus its validation status — "this is the definition, this is who owns it, this is whether it's currently known-good against the live schema." That combination (governed definition + live validation state, agent-retrievable) is the concrete answer to "deterministic and scalable."

### Rough phasing

**v1**: the model + CRUD + version lifecycle (reusing the `DataContract` DRAFT/ACTIVE/DEPRECATED pattern almost verbatim), no automated validation yet — this alone already solves "five people compute MRR five ways" by giving them one place to look. **v2**: lightweight validation (schema-shape check against dependencies, the way contract enforcement already works, without full query execution) on every scan/upload of a dependency, mirroring exactly how `evaluate_contract()` already piggybacks on `dataset_ingestion_service.sync_columns()`. **v3**: an execution adapter (optional, pluggable) that can actually run the expression against a connected warehouse for orgs that want DatFe to also return the live value, not just the definition — explicitly scoped as an add-on, not the default path.

---

## Direction 3: External reference reconciliation

### Why this is the hardest and least-built of the three

This is the direction where the codebase has almost nothing today beyond the one precedent worth generalizing (`dpdp_category`), and it's also the direction where "deterministic" is hardest to fully claim — reconciling a company's internal term against an external ontology is itself a semantic-matching problem, and semantic matching is inherently probabilistic at the edges even when the target taxonomy is fixed. Flagging this honestly: treat direction 3 as a research bet with a narrow, well-scoped pilot, not a committed roadmap item the way 1 and 2 can be.

### What "reconciliation" concretely means

When a model reasons about "customer lifetime value" using its general training, it has a prior — some generic, industry-average notion of what that term usually means and roughly how it's usually computed. That prior is frequently wrong for a specific company, and worse, the model doesn't know it's wrong; it states it with the same confidence it would state something the internal context actually supports. Reconciliation means building the explicit bridge: an internal `MetricDefinition` or `BusinessGlossaryTerm` gets an `external_reference_mappings` field — a small table of `(external_ontology, external_identifier, confidence, mapped_by, mapped_at)` — so that when a term matches or is related to something in a known external vocabulary (a standard financial metric taxonomy like FIBO for a finance-domain customer, `schema.org` types for anything web/product-adjacent, the DPDP/GDPR regulatory categories already partially implemented), that relationship is a stored, governed fact rather than something the model has to guess at fresh every time.

### The existing precedent, generalized

`privacy_engine.py`'s DPDP/GDPR category mapping is already exactly this pattern, just narrowly scoped to PII columns. The generalization is mechanical, not conceptual: the same `(internal_thing, external_vocabulary, external_identifier, confidence)` shape that already exists implicitly in `dpdp_category` should become an explicit, reusable table that any glossary term, metric, or dataset can attach to — not a bespoke mechanism reinvented per use case.

### How this changes what an agent gets back

Once this exists, `get_glossary_term("customer lifetime value")` (or the metric equivalent) can return not just the internal definition but "this maps to [external standard reference], confidence X, mapped by [steward]" — giving the model an explicit instruction to prefer the internal definition and *why* it differs from its prior, rather than silently overriding the model's own reasoning with no explanation, which is what pure RAG context injection does today (it changes the answer without ever addressing the model's competing prior directly).

### Recommended pilot scope

Don't start with an ambitious general-purpose ontology-mapping engine. Start narrow: (1) formalize the existing DPDP/GDPR mapping as the first `external_reference_mappings` entries and expose it via the MCP server's `describe_column` tool from direction 1 — this alone is shippable immediately, since the data already exists. (2) Pick one domain where a real customer has an existing, well-known external standard they care about (finance → FIBO-style regulatory metric definitions is a strong candidate given DatFe's existing DPDP/governance-first positioning) and hand-map a small number of terms as a proof of concept before investing in any matching automation. Automated/AI-assisted mapping suggestion (using the same embedding infrastructure from direction 1 to suggest candidate external matches for a steward to confirm, never auto-apply) is a reasonable v2, once the manual pattern is proven.

---

## How the three sequence together

MCP is the delivery mechanism — it's what turns "DatFe has good data" into "DatFe is something an agent can use," and it's buildable now, on what exists, with the least risk. The metrics layer is the deterministic backbone — it's what makes "scalable" true, because a governed definition scales the way a paragraph of prose repeated in five dashboards never will, and it's a natural sibling to the data contract pattern already built and battle-tested. The reconciliation layer is the differentiation multiplier — it's what makes the grounding actually correct against a model's competing prior instead of just present, but it's also the one genuine research bet of the three, and should be sized and resourced as one (a narrow pilot, not a platform commitment) until there's real signal on which external vocabularies actual customers care about.

Recommended build order: **MCP v1 first** (fastest, proves the thesis externally, reuses everything), **metrics layer v1 second** (clear, ownable differentiation, medium effort, reuses the `DataContract` lifecycle pattern almost directly), **reconciliation pilot third** (cheap to start narrow, given the DPDP precedent already exists — expand only once a specific customer's external-vocabulary need is concrete).
