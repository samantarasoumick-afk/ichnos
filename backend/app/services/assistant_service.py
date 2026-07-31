"""
Natural-language Q&A over the catalog.

When ANTHROPIC_API_KEY is configured, questions are answered by a real
LLM call (Anthropic Messages API, via raw HTTP - see
_call_anthropic_api), grounded in a context of org-level stats, the
full catalog directory, and detailed cards (including real DQ/
effective scores and lineage) for the handful of datasets/glossary
terms most relevant to the question, retrieved the same way the
semantic fallback below does. This is the primary path once a key is
set, and answers genuinely open-ended and multi-turn questions instead
of only the fixed intents below.

Without a key (or if the API call fails for any reason - network,
timeout, bad response), every question falls back to one of two
deterministic paths, unchanged from before:

  1. Intent detection: a handful of common governance questions (PII
     exposure, ownership, lineage, governance/maturity standing,
     contract health) are recognized by keyword and answered directly
     from real data via a template - these are the "simple" questions
     and the answers are exact, not generated.
  2. Semantic fallback: anything that doesn't match a known intent
     falls back to app.services.embedding_service's retrieval (real
     Voyage embeddings when VOYAGE_API_KEY is set and reachable,
     catalog_search_service's TF-IDF ranking otherwise) and returns
     the closest-matching datasets/glossary terms.
"""

import os
import re

import requests

from sqlalchemy.orm import Session

from app.models.business_process import BusinessProcess
from app.models.business_process import BusinessProcessLink
from app.models.column import DatasetColumn
from app.models.dataset import Dataset
from app.models.glossary_link import GlossaryTermLink
from app.models.governance import BusinessGlossaryTerm
from app.models.lineage import DatasetLineage
from app.models.risk import RiskDatasetLink
from app.models.source import DataSource

from app.models.data_quality import DataQuality

from app.services.catalog_search_service import build_result_snippet
from app.services.catalog_search_service import describe_document
from app.services.ecosystem_service import compute_source_rollup
from app.services.embedding_service import semantic_search
from app.services.lineage_quality_service import compute_effective_quality
from app.services.maturity_service import compute_maturity


ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_VERSION = "2023-06-01"
DEFAULT_ANTHROPIC_MODEL = "claude-sonnet-5"
DEFAULT_ANTHROPIC_MAX_TOKENS = 1024
DEFAULT_ANTHROPIC_TIMEOUT_SECONDS = 20

# How many prior turns (each a {"role", "text"} dict) to forward as
# conversation history, and how many semantically-retrieved documents
# to build detailed context cards for. Keeps the request bounded
# regardless of how long the conversation or catalog gets.
MAX_HISTORY_TURNS = 8
MAX_RETRIEVED_DETAIL_CARDS = 8
MAX_CATALOG_DIRECTORY_ROWS = 300

PII_KEYWORDS = ("pii", "sensitive", "personal data", "privacy risk", "high risk", "at risk")

OWNERSHIP_KEYWORDS = (
    "who owns", "owner of", "steward of",
    "who is responsible for", "who's responsible for"
)

LINEAGE_KEYWORDS = (
    "upstream", "downstream", "depends on", "dependency", "dependencies",
    "impact", "affects", "feeds into", "feeds from",
    "flow", "flows", "flowing", "trace", "traces", "tracing",
    "goes to", "moves to", "travels to"
)

GOVERNANCE_KEYWORDS = (
    "governance score", "maturity", "how are we doing", "governance status",
    "certification status", "how many datasets are certified"
)

# Deliberately separate from GOVERNANCE_KEYWORDS: "quality score"/"data
# quality" used to live in GOVERNANCE_KEYWORDS, which meant a question
# like "what's the quality score for X" (or just "how's data quality
# looking") got answered with org-wide governance maturity instead of
# the actual profiled/lineage-adjusted quality score - a real reported
# bug. Kept intentionally distinct from "governance" (certification/
# stewardship/contract coverage) even though both are "how healthy is
# this" questions, since they pull from different underlying data
# (DataQuality/compute_effective_quality vs compute_maturity).
QUALITY_KEYWORDS = (
    "data quality", "quality score", "dq score", "how clean", "how good is",
    "how accurate", "completeness", "uniqueness", "validity", "freshness",
    "consistency", "quality of", "data health"
)

CONTRACT_KEYWORDS = ("contract", "breach", "breached")

# "which sources/systems have PII" is asking for a system-level rollup
# (see the source-scope branch in _answer_pii_question below), not the
# usual per-dataset list - another reported bug where that phrasing
# came back with raw dataset rows instead of source names.
SOURCE_SCOPE_KEYWORDS = ("source", "sources", "system", "systems")

# Previously there was no dedicated handler for either of these at all
# - "what glossary terms are associated with X" and "which business
# process uses X" both fell straight through to the generic semantic-
# search fallback below, which searches the *entire* catalog for
# whatever's closest to the raw query text rather than "everything
# actually linked to this one dataset" - a reported bug where a
# glossary follow-up came back with a mix of on-topic and unrelated
# results, since nothing scoped the search to the dataset just asked
# about.
GLOSSARY_KEYWORDS = ("glossary", "business term", "defined term")

PROCESS_KEYWORDS = (
    "business process", "business processes",
    "which process", "what process", "which processes", "what processes"
)


def _dataset_directory_line(dataset: Dataset) -> str:
    bits = [f"{dataset.schema_name}.{dataset.name}"]
    if dataset.domain:
        bits.append(f"domain={dataset.domain}")
    if dataset.owner:
        bits.append(f"owner={dataset.owner}")
    if dataset.sensitivity_score:
        bits.append(f"sensitivity={dataset.sensitivity_score}")
    if dataset.governance_status:
        bits.append(f"governance={dataset.governance_status}")
    if dataset.certification:
        bits.append(f"certified={dataset.certification}")
    return "- " + " | ".join(bits)


def _dataset_lineage_labels(
    db: Session, dataset_id: str, datasets_by_id: dict
) -> tuple[list[str], list[str]]:

    def _label(other_id) -> str:
        found = datasets_by_id.get(str(other_id))
        return f"{found.schema_name}.{found.name}" if found else str(other_id)

    upstream = (
        db.query(DatasetLineage)
        .filter(DatasetLineage.downstream_dataset_id == dataset_id)
        .all()
    )
    downstream = (
        db.query(DatasetLineage)
        .filter(DatasetLineage.upstream_dataset_id == dataset_id)
        .all()
    )

    return (
        [_label(e.upstream_dataset_id) for e in upstream],
        [_label(e.downstream_dataset_id) for e in downstream],
    )


def _dataset_detail_card(db: Session, dataset: Dataset, datasets_by_id: dict) -> str:
    """Rich per-dataset context for the LLM: description, ownership,
    sensitivity, the *real* profiled/lineage-adjusted quality score
    (DataQuality.overall_score / compute_effective_quality - never the
    Dataset.quality_score heuristic, which is closer to a schema-hygiene
    score than genuine quality profiling), and lineage neighbors.
    """

    lines = [f"### Dataset: {dataset.schema_name}.{dataset.name}"]

    if dataset.description:
        lines.append(f"Description: {dataset.description}")
    elif dataset.ai_summary:
        lines.append(f"Summary: {dataset.ai_summary}")

    lines.append(
        f"Domain: {dataset.domain or 'none'} | Owner: {dataset.owner or 'unassigned'} | "
        f"Steward: {dataset.steward or 'unassigned'}"
    )
    lines.append(
        f"Sensitivity: {dataset.sensitivity_score or 'n/a'} "
        f"({dataset.pii_columns or 0} PII column(s)) | "
        f"Governance status: {dataset.governance_status or 'n/a'} | "
        f"Certification: {dataset.certification or 'none'}"
    )
    lines.append(f"Contract status: {dataset.contract_status or 'no active contract'}")

    effective = compute_effective_quality(dataset.id, db)
    own_score = effective.get("own_score")
    effective_score = effective.get("effective_score")
    if own_score is not None or effective_score is not None:
        lines.append(
            "Data quality: own score="
            f"{own_score if own_score is not None else 'unprofiled'}, "
            "effective (lineage-adjusted) score="
            f"{effective_score if effective_score is not None else 'n/a'}"
        )
    else:
        lines.append("Data quality: no profile yet")

    upstream_labels, downstream_labels = _dataset_lineage_labels(db, dataset.id, datasets_by_id)
    if upstream_labels:
        lines.append("Upstream (depends on): " + ", ".join(upstream_labels))
    if downstream_labels:
        lines.append("Downstream (would be affected): " + ", ".join(downstream_labels))

    return "\n".join(lines)


def _glossary_detail_card(term) -> str:
    lines = [f"### Glossary term: {term.term}"]
    if term.definition:
        lines.append(f"Definition: {term.definition}")
    if term.domain:
        lines.append(f"Domain: {term.domain}")
    if term.owner:
        lines.append(f"Owner: {term.owner}")
    return "\n".join(lines)


def _build_llm_context(
    db: Session, organization_id: str, datasets: list[Dataset], query: str
) -> tuple[str, list[dict]]:
    """Assembles the grounding context handed to the LLM: org-level
    stats, a full catalog directory (so the model knows what exists even
    beyond what's retrieved), and detailed cards for the handful of
    datasets/glossary terms most relevant to this specific question (via
    the same embedding_service retrieval used below). Returns the
    context text plus the retrieved items shaped as
    AskResponse sources, so the frontend can link straight to them.
    """

    sections = []

    maturity = compute_maturity(db, organization_id)
    sections.append(
        "## Organization overview\n"
        f"{len(datasets)} dataset(s) total. Governance maturity: {maturity['level']} "
        f"({maturity['overall_score']}/100). "
        f"{maturity['coverage']['pct_certified']}% certified, "
        f"{maturity['coverage']['pct_with_steward']}% have a steward, "
        f"{maturity['coverage']['pct_with_active_contract']}% under an active contract."
    )

    directory_rows = [_dataset_directory_line(d) for d in datasets[:MAX_CATALOG_DIRECTORY_ROWS]]
    directory_text = "\n".join(directory_rows)
    if len(datasets) > MAX_CATALOG_DIRECTORY_ROWS:
        remaining = len(datasets) - MAX_CATALOG_DIRECTORY_ROWS
        directory_text += f"\n... and {remaining} more dataset(s) not shown."
    sections.append("## Full catalog directory\n" + directory_text)

    # Scoped to dataset/glossary_term - catalog_search_service's corpus
    # now also covers processes/risks/controls/discussion threads (for
    # the global search bar), but the detail-card builders below only
    # know how to render those first two shapes.
    results = semantic_search(
        db, organization_id, query,
        top_k=MAX_RETRIEVED_DETAIL_CARDS,
        doc_types=("dataset", "glossary_term"),
    )
    sources: list[dict] = []

    if results:
        datasets_by_id = {str(d.id): d for d in datasets}
        cards = []
        for result in results:
            doc = result.document
            if doc.doc_type == "dataset":
                cards.append(_dataset_detail_card(db, doc.ref, datasets_by_id))
            else:
                cards.append(_glossary_detail_card(doc.ref))
            sources.append({"type": doc.doc_type, "id": doc.id, "label": doc.label})
        sections.append("## Most relevant to this question\n" + "\n\n".join(cards))

    return "\n\n".join(sections), sources


def _call_anthropic_api(system_prompt: str, messages: list[dict]) -> str | None:
    """Raw HTTP call to the Anthropic Messages API - uses the `requests`
    dependency already present in this project rather than adding the
    `anthropic` SDK, consistent with the minimal-dependency convention
    used elsewhere (e.g. no `slowapi` for rate limiting). Never raises:
    any failure (network, timeout, non-200, unexpected shape) returns
    None so the caller can fall back to the deterministic paths.
    """

    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        return None

    model = os.getenv("ANTHROPIC_MODEL", DEFAULT_ANTHROPIC_MODEL)
    max_tokens = int(os.getenv("ANTHROPIC_MAX_TOKENS", str(DEFAULT_ANTHROPIC_MAX_TOKENS)))
    timeout = int(os.getenv("ANTHROPIC_TIMEOUT_SECONDS", str(DEFAULT_ANTHROPIC_TIMEOUT_SECONDS)))

    try:
        response = requests.post(
            ANTHROPIC_API_URL,
            headers={
                "x-api-key": api_key,
                "anthropic-version": ANTHROPIC_VERSION,
                "content-type": "application/json",
            },
            json={
                "model": model,
                "max_tokens": max_tokens,
                "system": system_prompt,
                "messages": messages,
            },
            timeout=timeout,
        )
        response.raise_for_status()
        data = response.json()
        text = "".join(
            block.get("text", "")
            for block in data.get("content", [])
            if block.get("type") == "text"
        ).strip()
        return text or None
    except (requests.exceptions.RequestException, ValueError, KeyError, AttributeError):
        return None


def _try_llm_answer(
    query: str,
    context: str,
    sources: list[dict],
    history: list[dict] | None = None,
) -> dict | None:
    """Real LLM-backed answer, grounded in the context _build_llm_context
    assembled. Returns None (never raises) on a missing API key or any
    downstream failure, so answer_question() falls through to the
    deterministic paths exactly as it did before this was implemented -
    existing tests, which never set ANTHROPIC_API_KEY, keep exercising
    that fallback path unmodified.
    """

    if not os.getenv("ANTHROPIC_API_KEY"):
        return None

    system_prompt = (
        "You are the embedded assistant inside DatFe, a data catalog and "
        "governance platform. Answer the user's question using ONLY the "
        "catalog context provided below - never invent dataset names, "
        "owners, scores, or relationships that aren't present in it. If "
        "the context doesn't contain what's needed to answer, say so "
        "plainly and suggest what the user could look at instead. "
        "Reference datasets in schema.name form. Keep answers concise.\n\n"
        + context
    )

    messages = []
    for turn in (history or [])[-MAX_HISTORY_TURNS:]:
        role = turn.get("role")
        text = turn.get("text")
        if role in ("user", "assistant") and text:
            messages.append({"role": role, "content": text})
    messages.append({"role": "user", "content": query})

    answer = _call_anthropic_api(system_prompt, messages)
    if answer is None:
        return None

    return {"answer": answer, "sources": sources}


def _compact(text: str) -> str:
    """Lowercased, alphanumeric-only. Lets a question typed as one
    compound word ("salesforceCRM", "SalesforceCRM") match a schema or
    source name that's actually spaced/underscored/differently-cased
    ("Salesforce CRM", "salesforce_crm") - plain substring matching on
    the raw query would miss all of those.
    """
    return "".join(ch for ch in text.lower() if ch.isalnum())


def _find_mentioned_dataset(datasets: list[Dataset], normalized_query: str) -> Dataset | None:
    """
    Longest-name-first match against either the dataset's own name or
    its schema name, compared with spacing/case/punctuation stripped
    out - so "customer_orders" being asked about doesn't get shadowed
    by a shorter "customers" dataset that also happens to
    substring-match, and a schema like "salesforce" is matched too, not
    just the table name.
    """

    compact_query = _compact(normalized_query)

    candidates = []
    for dataset in datasets:
        for name in (dataset.name, dataset.schema_name):
            if not name:
                continue
            compact_name = _compact(name)
            if compact_name and compact_name in compact_query:
                candidates.append((dataset, compact_name))
                break

    if not candidates:
        return None

    return max(candidates, key=lambda pair: len(pair[1]))[0]


def _resolve_query_scope(
    datasets: list[Dataset],
    sources: list[DataSource],
    normalized_query: str,
) -> tuple[str, list[Dataset]]:
    """
    Resolves the system/dataset a lineage question is actually about,
    trying progressively broader matches: a specific dataset name
    first (most precise - a single table), then a source name (e.g.
    "Salesforce CRM" - everything that system feeds), then a shared
    schema name (e.g. "salesforce" alone, which is how datasets
    ingested from a source are actually grouped). Returns (label,
    scope) where scope is every dataset the matched entity resolves
    to - exactly one for a dataset-name match, potentially several for
    a source/schema match. Returns ("", []) if nothing in the question
    matches anything in the catalog.

    This exists because a question like "where is data from Salesforce
    flowing" names a *system*, not a single table - the old
    dataset-name-only match could never resolve it, since no dataset
    is literally named "salesforce" (the tables underneath it are
    "leads", "opportunities", etc., sharing schema_name="salesforce").
    """

    compact_query = _compact(normalized_query)

    dataset_candidates = []
    for dataset in datasets:
        if dataset.name:
            compact_name = _compact(dataset.name)
            if compact_name and compact_name in compact_query:
                dataset_candidates.append((dataset, compact_name))

    if dataset_candidates:
        best = max(dataset_candidates, key=lambda pair: len(pair[1]))[0]
        return f"{best.schema_name}.{best.name}", [best]

    source_candidates = []
    for source in sources:
        if source.name:
            compact_name = _compact(source.name)
            if compact_name and compact_name in compact_query:
                source_candidates.append((source, compact_name))

    if source_candidates:
        best_source = max(source_candidates, key=lambda pair: len(pair[1]))[0]
        matched = [d for d in datasets if d.source_id == best_source.id]
        if matched:
            return best_source.name, matched

    schema_candidates = []
    for schema in {d.schema_name for d in datasets if d.schema_name}:
        compact_name = _compact(schema)
        if compact_name and compact_name in compact_query:
            schema_candidates.append((schema, compact_name))

    if schema_candidates:
        best_schema = max(schema_candidates, key=lambda pair: len(pair[1]))[0]
        matched = [d for d in datasets if d.schema_name == best_schema]
        if matched:
            return best_schema, matched

    return "", []


# Word-boundary (not substring) match on purpose - "it" as a bare
# substring is inside "quality", "identifier", "sensitivity" and would
# false-positive on nearly every question. Used to gate the quality
# handler's history fallback (see _answer_quality_question) - a
# referential pronoun is what actually signals "this question is a
# follow-up about the same thing as before", as opposed to a
# freestanding org-wide question like "how's our data quality looking".
_REFERENTIAL_PRONOUN_RE = re.compile(r"\b(it|its|this|that|these|those)\b")


def _has_referential_pronoun(normalized_query: str) -> bool:
    return bool(_REFERENTIAL_PRONOUN_RE.search(normalized_query))


def _find_mentioned_dataset_with_history(
    datasets: list[Dataset],
    normalized_query: str,
    history: list[dict] | None,
) -> Dataset | None:
    """
    Same as _find_mentioned_dataset, but falls back to the conversation
    history when the current question doesn't name anything itself -
    a follow-up like "who owns it" or "is that PII" never mentions a
    dataset by name, so without this the deterministic handlers below
    had no way to know what "it"/"that" referred to and would forget
    the subject the moment the very next question was asked (a real
    reported bug: "public.customers" from the first answer meant
    nothing to the second question). Walks backwards through prior
    turns - most recent first - since that's whatever the conversation
    was just about; reuses the exact same name-matching logic against
    each turn's raw text rather than a separate resolution path.
    """

    dataset = _find_mentioned_dataset(datasets, normalized_query)
    if dataset is not None:
        return dataset

    if not history:
        return None

    for turn in reversed(history):
        text = (turn.get("text") or "").lower().strip()
        if not text:
            continue
        dataset = _find_mentioned_dataset(datasets, text)
        if dataset is not None:
            return dataset

    return None


def _resolve_query_scope_with_history(
    datasets: list[Dataset],
    sources: list[DataSource],
    normalized_query: str,
    history: list[dict] | None,
) -> tuple[str, list[Dataset]]:
    """The lineage intent's equivalent of
    _find_mentioned_dataset_with_history - falls back to conversation
    history for the broader dataset/source/schema scope resolution
    lineage questions use, so "what about its downstream tables?"
    resolves against whatever system/dataset the conversation was just
    about instead of coming back empty.
    """

    label, scope = _resolve_query_scope(datasets, sources, normalized_query)
    if scope:
        return label, scope

    if not history:
        return label, scope

    for turn in reversed(history):
        text = (turn.get("text") or "").lower().strip()
        if not text:
            continue
        label, scope = _resolve_query_scope(datasets, sources, text)
        if scope:
            return label, scope

    return "", []


def _answer_pii_question(
    datasets: list[Dataset],
    sources: list[DataSource],
    normalized_query: str,
) -> dict | None:

    if not any(keyword in normalized_query for keyword in PII_KEYWORDS):
        return None

    # "which sources/systems have PII" is a question about systems, not
    # tables - answer it with a per-source rollup (same numbers the
    # Ecosystem View shows, via the shared compute_source_rollup) rather
    # than falling through to the dataset-level list below, which used
    # to be the only answer this intent could ever give.
    if any(keyword in normalized_query for keyword in SOURCE_SCOPE_KEYWORDS):
        datasets_by_source: dict[str, list[Dataset]] = {}
        for dataset in datasets:
            datasets_by_source.setdefault(dataset.source_id, []).append(dataset)

        source_by_id = {source.id: source for source in sources}
        rollups = []
        for source_id, source_datasets in datasets_by_source.items():
            source = source_by_id.get(source_id)
            if source is None:
                continue
            rollup = compute_source_rollup(source_datasets)
            if rollup["pii_columns"] > 0:
                rollups.append((source, rollup))

        if not rollups:
            return {
                "answer": "None of your connected sources currently carry PII columns.",
                "sources": [],
            }

        rollups.sort(key=lambda pair: pair[1]["pii_columns"], reverse=True)

        lines = [
            f"- {source.name} ({rollup['pii_columns']} PII column(s) across "
            f"{rollup['dataset_count']} dataset(s))"
            for source, rollup in rollups
        ]

        answer = (
            f"{len(rollups)} source(s) carry PII data. Highest first:\n" + "\n".join(lines)
        )

        return {
            "answer": answer,
            "sources": [
                {"type": "source", "id": source.id, "label": source.name}
                for source, _ in rollups
            ],
        }

    at_risk = [d for d in datasets if d.sensitivity_score in ("MEDIUM", "HIGH")]

    if not at_risk:
        return {
            "answer": "None of your datasets currently carry a MEDIUM or HIGH sensitivity classification.",
            "sources": [],
        }

    at_risk.sort(key=lambda d: {"HIGH": 0, "MEDIUM": 1}.get(d.sensitivity_score, 2))
    top = at_risk[:10]

    lines = [
        f"- {d.schema_name}.{d.name} ({d.sensitivity_score}, {d.pii_columns} PII column(s))"
        for d in top
    ]

    answer = (
        f"{len(at_risk)} dataset(s) carry meaningful personal-data risk. Highest first:\n"
        + "\n".join(lines)
    )

    return {
        "answer": answer,
        "sources": [
            {"type": "dataset", "id": d.id, "label": f"{d.schema_name}.{d.name}"}
            for d in top
        ],
    }


def _answer_ownership_question(
    datasets: list[Dataset],
    normalized_query: str,
    history: list[dict] | None = None,
) -> dict | None:

    if not any(keyword in normalized_query for keyword in OWNERSHIP_KEYWORDS):
        return None

    dataset = _find_mentioned_dataset_with_history(datasets, normalized_query, history)

    if dataset is None:
        return {
            "answer": (
                "I can answer ownership questions once you name a specific dataset - "
                "try something like \"who owns customers\"."
            ),
            "sources": [],
        }

    owner = dataset.owner or "no documented owner"
    steward = dataset.steward or "no documented steward"

    return {
        "answer": f"{dataset.schema_name}.{dataset.name} is owned by {owner}, stewarded by {steward}.",
        "sources": [
            {"type": "dataset", "id": dataset.id, "label": f"{dataset.schema_name}.{dataset.name}"}
        ],
    }


def _answer_lineage_question(
    db: Session,
    datasets: list[Dataset],
    sources: list[DataSource],
    normalized_query: str,
    history: list[dict] | None = None,
) -> dict | None:

    if not any(keyword in normalized_query for keyword in LINEAGE_KEYWORDS):
        return None

    label, scope = _resolve_query_scope_with_history(datasets, sources, normalized_query, history)

    if not scope:
        return {
            "answer": (
                "I can answer lineage questions once you name a specific dataset or "
                "system - try something like \"what's downstream of orders\" or "
                "\"where is data from Salesforce flowing\"."
            ),
            "sources": [],
        }

    scope_ids = {d.id for d in scope}
    dataset_by_id = {d.id: d for d in datasets}

    def _label(dataset_id):
        found = dataset_by_id.get(dataset_id)
        return f"{found.schema_name}.{found.name}" if found else dataset_id

    upstream_edges = (
        db.query(DatasetLineage)
        .filter(DatasetLineage.downstream_dataset_id.in_(scope_ids))
        .all()
    )
    downstream_edges = (
        db.query(DatasetLineage)
        .filter(DatasetLineage.upstream_dataset_id.in_(scope_ids))
        .all()
    )

    # Only edges that actually leave the resolved scope - two datasets
    # under the same source feeding each other is internal to that
    # system, not "upstream/downstream of it".
    upstream_ids = sorted({
        e.upstream_dataset_id for e in upstream_edges
        if e.upstream_dataset_id not in scope_ids
    })
    downstream_ids = sorted({
        e.downstream_dataset_id for e in downstream_edges
        if e.downstream_dataset_id not in scope_ids
    })

    # A question like "where is Salesforce PII data flowing" is asking
    # two things at once - lineage AND privacy. Answering only the
    # lineage half (a bare list of downstream tables) misses the point
    # of the question, so when a PII keyword is also present, call out
    # which of those downstream datasets carry personal data themselves.
    wants_pii_focus = any(keyword in normalized_query for keyword in PII_KEYWORDS)

    lines = [f"{label}:" if len(scope) > 1 else label]

    if upstream_ids:
        lines.append("Upstream (feeds into this): " + ", ".join(_label(i) for i in upstream_ids))

    if downstream_ids:
        lines.append(
            ("Downstream (data from here flows into): " if wants_pii_focus else "Downstream (would be affected): ")
            + ", ".join(_label(i) for i in downstream_ids)
        )

        if wants_pii_focus:
            pii_hits = [
                i for i in downstream_ids
                if dataset_by_id.get(i) and (dataset_by_id[i].pii_columns or 0) > 0
            ]
            if pii_hits:
                lines.append(
                    "Of those, these downstream dataset(s) also carry PII columns of their own: "
                    + ", ".join(
                        f"{_label(i)} ({dataset_by_id[i].pii_columns} PII column(s))"
                        for i in pii_hits
                    )
                )
            else:
                lines.append(
                    "None of those downstream datasets have their own columns classified as "
                    "PII yet - the personal data may still be flowing through unclassified, "
                    "so it's worth a rescan or a manual check."
                )

    if not upstream_ids and not downstream_ids:
        lines.append("No lineage relationships are recorded for this yet.")

    result_sources = [
        {"type": "dataset", "id": d.id, "label": f"{d.schema_name}.{d.name}"}
        for d in scope
    ]
    result_sources += [
        {"type": "dataset", "id": i, "label": _label(i)}
        for i in list(upstream_ids) + list(downstream_ids)
    ]

    return {
        "answer": "\n".join(lines),
        "sources": result_sources,
    }


def _answer_quality_question(
    db: Session,
    datasets: list[Dataset],
    normalized_query: str,
    history: list[dict] | None = None,
) -> dict | None:
    """
    Answers "how's data quality / what's the quality score / how
    complete is X" questions with the real profiled numbers
    (DataQuality's dimension scores plus compute_effective_quality's
    lineage-adjusted score) - previously "quality score" lived in
    GOVERNANCE_KEYWORDS, so these questions were silently answered with
    org-wide governance maturity instead, which is a different metric
    entirely (certification/stewardship/contract coverage, not
    completeness/uniqueness/validity/freshness/consistency).

    Unlike ownership/lineage (which always need a specific dataset and
    have no other useful answer to give), quality has a genuinely
    meaningful org-wide answer when nothing is named - so the history
    fallback here is gated on an actual referential pronoun ("it",
    "this", etc.) rather than applied unconditionally. Without that
    gate, a freestanding org-wide question like "how's our data quality
    looking?" asked right after a dataset-specific question would
    wrongly latch onto that prior dataset instead of giving the
    intended org-wide summary - a real regression caught while
    verifying the conversation-memory fix.
    """

    if not any(keyword in normalized_query for keyword in QUALITY_KEYWORDS):
        return None

    dataset = _find_mentioned_dataset(datasets, normalized_query)
    if dataset is None and _has_referential_pronoun(normalized_query):
        dataset = _find_mentioned_dataset_with_history(datasets, normalized_query, history)

    if dataset is not None:
        label = f"{dataset.schema_name}.{dataset.name}"
        effective = compute_effective_quality(dataset.id, db)
        own_score = effective.get("own_score")
        effective_score = effective.get("effective_score")

        if own_score is None and effective_score is None:
            answer = (
                f"{label} hasn't been profiled for data quality yet - no "
                "completeness/uniqueness/validity/freshness/consistency scan has "
                "run against it."
            )
        else:
            lines = [
                f"{label}: own quality score = "
                f"{own_score if own_score is not None else 'unprofiled'}/100, "
                "effective (lineage-adjusted) score = "
                f"{effective_score if effective_score is not None else 'n/a'}/100."
            ]

            dq = db.query(DataQuality).filter(DataQuality.dataset_id == dataset.id).first()
            if dq:
                dims = [
                    f"{name}={round(value, 1)}"
                    for name, value in (
                        ("completeness", dq.completeness),
                        ("uniqueness", dq.uniqueness),
                        ("validity", dq.validity),
                        ("freshness", dq.freshness),
                        ("consistency", dq.consistency),
                    )
                    if value is not None
                ]
                if dims:
                    lines.append("Dimension breakdown: " + ", ".join(dims))

            if effective.get("contributing_edges"):
                lines.append(
                    f"That effective score is lineage-adjusted from "
                    f"{len(effective['contributing_edges'])} upstream source(s)."
                )

            answer = "\n".join(lines)

        return {
            "answer": answer,
            "sources": [{"type": "dataset", "id": dataset.id, "label": label}],
        }

    # No specific dataset named - an org-wide quality summary: coverage
    # (how many datasets have actually been profiled) plus the
    # lowest-scoring handful, since those are what's most worth a
    # rescan or a closer look.
    profiled: list[tuple[Dataset, float]] = []
    for d in datasets:
        effective = compute_effective_quality(d.id, db)
        score = effective.get("effective_score")
        if score is not None:
            profiled.append((d, score))

    if not profiled:
        return {
            "answer": (
                "None of your datasets have a data quality profile yet - run a scan to "
                "get completeness/uniqueness/validity/freshness/consistency scores."
            ),
            "sources": [],
        }

    avg_score = round(sum(score for _, score in profiled) / len(profiled), 1)
    profiled.sort(key=lambda pair: pair[1])
    worst = profiled[:5]

    answer = (
        f"{len(profiled)} of {len(datasets)} dataset(s) have a quality profile. "
        f"Average effective quality score: {avg_score}/100.\n"
        "Lowest-scoring: "
        + ", ".join(f"{d.schema_name}.{d.name} ({score}/100)" for d, score in worst)
    )

    return {
        "answer": answer,
        "sources": [
            {"type": "dataset", "id": d.id, "label": f"{d.schema_name}.{d.name}"}
            for d, _ in worst
        ],
    }


def _answer_glossary_question(
    db: Session,
    datasets: list[Dataset],
    normalized_query: str,
    history: list[dict] | None = None,
) -> dict | None:
    """
    Answers "what glossary terms are associated/linked to X" from the
    real, explicit GlossaryTermLink rows for the resolved dataset -
    previously there was no dedicated handler for this at all, so it
    fell straight through to the generic semantic-search fallback,
    which ranks the *entire* corpus (every dataset and glossary term in
    the org) against the raw query text instead of "everything actually
    linked to this one dataset". That's what produced the reported
    symptom: a follow-up like "what glossary terms are associated"
    coming back with a mix of on-topic and unrelated hits, since nothing
    scoped the search to the dataset the conversation was just about.
    """

    if not any(keyword in normalized_query for keyword in GLOSSARY_KEYWORDS):
        return None

    dataset = _find_mentioned_dataset_with_history(datasets, normalized_query, history)

    if dataset is None:
        return {
            "answer": (
                "I can look up glossary terms once you name a specific dataset - "
                "try something like \"what glossary terms are linked to customers?\"."
            ),
            "sources": [],
        }

    label = f"{dataset.schema_name}.{dataset.name}"

    rows = (
        db.query(GlossaryTermLink, BusinessGlossaryTerm, DatasetColumn)
        .join(BusinessGlossaryTerm, GlossaryTermLink.term_id == BusinessGlossaryTerm.id)
        .outerjoin(DatasetColumn, GlossaryTermLink.column_id == DatasetColumn.id)
        .filter(GlossaryTermLink.dataset_id == dataset.id)
        .all()
    )

    if not rows:
        return {
            "answer": f"No glossary terms are linked to {label} yet.",
            "sources": [{"type": "dataset", "id": dataset.id, "label": label}],
        }

    lines = [
        f"- {term.term}" + (f" (on column {column.name})" if column else " (whole dataset)")
        for _link, term, column in rows
    ]

    answer = f"{len(rows)} glossary term(s) linked to {label}:\n" + "\n".join(lines)

    return {
        "answer": answer,
        # The dataset itself comes first (not just the terms) so a
        # follow-up ("what's downstream of it?") still has a dataset to
        # resolve against via _primary_dataset_from_sources/history -
        # otherwise the conversation's subject would be lost the moment
        # a glossary question was asked about it.
        "sources": [
            {"type": "dataset", "id": dataset.id, "label": label},
            *[
                {"type": "glossary_term", "id": term.id, "label": term.term}
                for _link, term, _column in rows
            ],
        ],
    }


def _answer_process_question(
    db: Session,
    datasets: list[Dataset],
    normalized_query: str,
    history: list[dict] | None = None,
) -> dict | None:
    """
    Same idea as _answer_glossary_question, for "which business process
    uses X" - the explicit BusinessProcessLink rows for the resolved
    dataset, instead of an unscoped semantic-search fallback.
    """

    if not any(keyword in normalized_query for keyword in PROCESS_KEYWORDS):
        return None

    dataset = _find_mentioned_dataset_with_history(datasets, normalized_query, history)

    if dataset is None:
        return {
            "answer": (
                "I can look up business processes once you name a specific dataset - "
                "try something like \"which business process uses customers?\"."
            ),
            "sources": [],
        }

    label = f"{dataset.schema_name}.{dataset.name}"

    rows = (
        db.query(BusinessProcess)
        .join(BusinessProcessLink, BusinessProcessLink.process_id == BusinessProcess.id)
        .filter(BusinessProcessLink.dataset_id == dataset.id)
        .all()
    )

    if not rows:
        return {
            "answer": f"No business process is linked to {label} yet.",
            "sources": [{"type": "dataset", "id": dataset.id, "label": label}],
        }

    lines = [
        f"- {process.name}" + (f" (owner: {process.owner})" if process.owner else "")
        for process in rows
    ]

    answer = f"{label} is used by {len(rows)} business process(es):\n" + "\n".join(lines)

    return {
        "answer": answer,
        # Dataset first, same reasoning as _answer_glossary_question -
        # keeps it resolvable as the conversation's subject for a
        # further follow-up.
        "sources": [
            {"type": "dataset", "id": dataset.id, "label": label},
            *[
                {"type": "process", "id": process.id, "label": process.name}
                for process in rows
            ],
        ],
    }


def _answer_governance_question(
    db: Session,
    organization_id: str,
    normalized_query: str,
) -> dict | None:

    if not any(keyword in normalized_query for keyword in GOVERNANCE_KEYWORDS):
        return None

    maturity = compute_maturity(db, organization_id)

    answer = (
        f"Governance maturity: {maturity['level']} ({maturity['overall_score']}/100) across "
        f"{maturity['total_datasets']} dataset(s). "
        f"{maturity['coverage']['pct_certified']}% certified, "
        f"{maturity['coverage']['pct_with_steward']}% have a real steward, "
        f"{maturity['coverage']['pct_with_active_contract']}% under an active contract."
    )

    if maturity["recommended_next_steps"]:
        answer += "\n\nTop recommendation: " + maturity["recommended_next_steps"][0]

    return {"answer": answer, "sources": []}


def _answer_contract_question(datasets: list[Dataset], normalized_query: str) -> dict | None:

    if not any(keyword in normalized_query for keyword in CONTRACT_KEYWORDS):
        return None

    breached = [d for d in datasets if d.contract_status == "BREACHED"]
    compliant = [d for d in datasets if d.contract_status == "COMPLIANT"]

    if breached:
        lines = [f"{d.schema_name}.{d.name}" for d in breached]
        answer = f"{len(breached)} dataset(s) currently have a breached contract: " + ", ".join(lines)
    elif compliant:
        answer = f"{len(compliant)} dataset(s) have an active, compliant data contract. No breaches right now."
    else:
        answer = "No datasets have an active data contract yet."

    return {
        "answer": answer,
        "sources": [
            {"type": "dataset", "id": d.id, "label": f"{d.schema_name}.{d.name}"}
            for d in breached
        ],
    }


def _answer_via_semantic_search(db: Session, organization_id: str, query: str) -> dict:
    """
    The last-resort fallback: nothing above matched a known intent, so
    rank the whole catalog against the raw query text and describe
    whatever comes back closest. Deliberately unscoped to all 8 entity
    types GET /api/search covers (source/dataset/column/glossary_term/
    process/risk/control/discussion_thread) - it used to be hardcoded to
    just dataset+glossary_term, which meant this fallback and the actual
    search bar could disagree about whether something "exists" in the
    catalog for the exact same query. Reuses describe_document() (the
    same subtitle/url builder GET /api/search and the "@" mention picker
    already share) and build_result_snippet() so a result reads
    identically everywhere it shows up, one shared engine, not three
    separate renderings of the same underlying match.
    """

    results = semantic_search(db, organization_id, query, top_k=5)

    if not results:
        return {
            "answer": (
                "I couldn't find anything in your catalog that matches this question. "
                "Try mentioning a dataset, domain, or glossary term by name."
            ),
            "sources": [],
        }

    lines = []
    sources = []

    for result in results:

        doc = result.document
        subtitle, url = describe_document(doc)
        snippet = build_result_snippet(doc.text, doc.label)

        detail = " · ".join(bit for bit in (subtitle, snippet) if bit)
        lines.append(f"- {doc.label}: {detail}" if detail else f"- {doc.label}")
        sources.append({"type": doc.doc_type, "id": doc.id, "label": doc.label, "url": url})

    answer = "Here's what I found related to your question:\n" + "\n".join(lines)

    return {"answer": answer, "sources": sources}


def _answer_question_core(
    db: Session,
    organization_id: str,
    query: str,
    history: list[dict] | None = None,
) -> dict:

    datasets = (
        db.query(Dataset)
        .filter(Dataset.organization_id == organization_id)
        .all()
    )

    if not datasets:
        return {
            "answer": (
                "There's nothing in your catalog yet - connect a source or upload "
                "a CSV to get started."
            ),
            "sources": [],
        }

    # Only pay for context-building (semantic retrieval + a per-dataset
    # effective-quality/lineage lookup for each retrieved item) when a key
    # is actually configured - keeps the no-key path exactly as cheap as
    # it was before this was implemented.
    if os.getenv("ANTHROPIC_API_KEY"):
        context, sources = _build_llm_context(db, organization_id, datasets, query)
        llm_answer = _try_llm_answer(query, context, sources, history=history)
        if llm_answer is not None:
            return llm_answer

    normalized_query = query.lower().strip()

    data_sources = (
        db.query(DataSource)
        .filter(DataSource.organization_id == organization_id)
        .all()
    )

    # Checked before the plain PII intent below: a question that
    # mentions both a system/dataset AND PII/lineage wording (e.g.
    # "where is Salesforce PII data flowing") is a lineage question
    # with a privacy angle, not a request for the org-wide PII list -
    # if it matched the PII intent first, the specific system named in
    # the question would just get ignored. _answer_lineage_question
    # itself folds in PII context (see wants_pii_focus above) when
    # both kinds of keywords are present, so nothing is lost by
    # checking it first.
    result = _answer_lineage_question(db, datasets, data_sources, normalized_query, history=history)
    if result is not None:
        return result

    result = _answer_pii_question(datasets, data_sources, normalized_query)
    if result is not None:
        return result

    result = _answer_ownership_question(datasets, normalized_query, history=history)
    if result is not None:
        return result

    # Checked before governance: "quality score"/"data quality" wording
    # is about the profiled DataQuality/effective-quality numbers, a
    # different metric than governance maturity - see QUALITY_KEYWORDS.
    result = _answer_quality_question(db, datasets, normalized_query, history=history)
    if result is not None:
        return result

    # Checked before the semantic-search fallback: previously neither of
    # these had a dedicated handler at all, so "what glossary terms are
    # associated with X" / "which business process uses X" fell through
    # to the unscoped semantic search below - see GLOSSARY_KEYWORDS/
    # PROCESS_KEYWORDS above for why that produced a mix of relevant and
    # irrelevant results.
    result = _answer_glossary_question(db, datasets, normalized_query, history=history)
    if result is not None:
        return result

    result = _answer_process_question(db, datasets, normalized_query, history=history)
    if result is not None:
        return result

    result = _answer_governance_question(db, organization_id, normalized_query)
    if result is not None:
        return result

    result = _answer_contract_question(datasets, normalized_query)
    if result is not None:
        return result

    return _answer_via_semantic_search(db, organization_id, query)


# Keyword sets already defined above double as the signal for "which
# angle has this conversation already covered" - re-scanning the raw
# query text works uniformly whether the question was actually
# answered by a deterministic intent handler, the LLM path, or the
# semantic-search fallback, rather than threading a category label
# through every branch above individually. "quality" now maps to its
# own QUALITY_KEYWORDS (previously aliased to GOVERNANCE_KEYWORDS,
# which is what caused quality questions to be answered as governance
# maturity in the first place - see _answer_quality_question above).
# "glossary"/"process" are new alongside _answer_glossary_question/
# _answer_process_question above.
_CATEGORY_KEYWORDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("pii", PII_KEYWORDS),
    ("lineage", LINEAGE_KEYWORDS),
    ("governance", GOVERNANCE_KEYWORDS),
    ("quality", QUALITY_KEYWORDS),
    ("contract", CONTRACT_KEYWORDS),
    ("ownership", OWNERSHIP_KEYWORDS),
    ("glossary", GLOSSARY_KEYWORDS),
    ("process", PROCESS_KEYWORDS),
)


def _already_asked_categories(query: str) -> set[str]:
    normalized = query.lower().strip()
    return {
        category for category, keywords in _CATEGORY_KEYWORDS
        if any(keyword in normalized for keyword in keywords)
    }


def _primary_dataset_from_sources(db: Session, sources: list[dict]) -> Dataset | None:
    for source in sources:
        if source.get("type") == "dataset":
            return db.query(Dataset).filter(Dataset.id == source["id"]).first()
    return None


def _build_follow_up_suggestions(
    db: Session,
    dataset: Dataset,
    already_asked: set[str],
) -> list[dict]:
    """
    Suggests up to four natural next questions about the same dataset
    this answer was about, each pointing at a different connected
    attribute (glossary, business process, contract, data quality,
    risk/controls, lineage, trust, the system it belongs to) than
    whatever this question already covered - so a conversation walks
    the connected graph one hop at a time instead of circling the same
    angle. Existence-gated where that's cheap to check (glossary/
    process/risk links) so a suggestion never points at something
    that turns out to be empty; always-offered for angles every
    dataset has an answer to regardless (contract status, quality
    score, trust score, its source) even when the honest answer is
    "none yet" - that's still a useful thing to learn.
    """

    label = f"{dataset.schema_name}.{dataset.name}"
    candidates: list[tuple[str, dict]] = []

    has_glossary = (
        db.query(GlossaryTermLink)
        .filter(GlossaryTermLink.dataset_id == dataset.id)
        .first()
        is not None
    )
    if has_glossary:
        candidates.append((
            "glossary",
            {"label": "Glossary terms", "query": f"What glossary terms are linked to {label}?"},
        ))

    has_process = (
        db.query(BusinessProcessLink)
        .filter(BusinessProcessLink.dataset_id == dataset.id)
        .first()
        is not None
    )
    if has_process:
        candidates.append((
            "process",
            {"label": "Business process", "query": f"Which business process uses {label}?"},
        ))

    has_risk = (
        db.query(RiskDatasetLink)
        .filter(RiskDatasetLink.dataset_id == dataset.id)
        .first()
        is not None
    )
    if has_risk:
        candidates.append((
            "risk",
            {"label": "Risks & controls", "query": f"What risks and controls are logged against {label}?"},
        ))

    candidates.append((
        "lineage",
        {"label": "Lineage", "query": f"What's downstream of {dataset.name}?"},
    ))
    candidates.append((
        "contract",
        {"label": "Data contract", "query": f"Does {label} have a data contract?"},
    ))
    candidates.append((
        "quality",
        {"label": "Data quality", "query": f"What's the data quality score for {label}?"},
    ))
    candidates.append((
        "systems",
        {"label": "Source system", "query": f"Which system does {label} belong to?"},
    ))
    candidates.append((
        "pii",
        {"label": "PII", "query": f"Does {label} contain PII?"},
    ))

    return [
        suggestion for category, suggestion in candidates
        if category not in already_asked
    ][:4]


def answer_question(
    db: Session,
    organization_id: str,
    query: str,
    history: list[dict] | None = None,
) -> dict:
    """
    Thin wrapper around _answer_question_core: same answer as before,
    plus a `follow_up_suggestions` list built from whatever the
    answer's primary dataset is actually connected to - the "keep
    building on what's been asked" behavior, since DatFe already has
    all of these relationships (glossary, process, contract, risk,
    lineage) modeled and linked, not just the dataset in isolation.
    """

    result = _answer_question_core(db, organization_id, query, history=history)

    dataset = _primary_dataset_from_sources(db, result.get("sources", []))
    if dataset is not None:
        already_asked = _already_asked_categories(query)
        result["follow_up_suggestions"] = _build_follow_up_suggestions(db, dataset, already_asked)
    else:
        result["follow_up_suggestions"] = []

    return result
