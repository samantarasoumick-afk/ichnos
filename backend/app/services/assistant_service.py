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

import requests

from sqlalchemy.orm import Session

from app.models.dataset import Dataset
from app.models.lineage import DatasetLineage

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
    "impact", "affects", "feeds into", "feeds from"
)

GOVERNANCE_KEYWORDS = (
    "governance score", "maturity", "how are we doing", "governance status",
    "certification status", "how many datasets are certified", "quality score"
)

CONTRACT_KEYWORDS = ("contract", "breach", "breached")


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


def _find_mentioned_dataset(datasets: list[Dataset], normalized_query: str) -> Dataset | None:
    """
    Longest-name-first substring match, so "customer_orders" being
    asked about doesn't get shadowed by a shorter "customers" dataset
    that also happens to substring-match.
    """

    candidates = [
        dataset for dataset in datasets
        if dataset.name and dataset.name.lower() in normalized_query
    ]

    if not candidates:
        return None

    return max(candidates, key=lambda dataset: len(dataset.name))


def _answer_pii_question(datasets: list[Dataset], normalized_query: str) -> dict | None:

    if not any(keyword in normalized_query for keyword in PII_KEYWORDS):
        return None

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


def _answer_ownership_question(datasets: list[Dataset], normalized_query: str) -> dict | None:

    if not any(keyword in normalized_query for keyword in OWNERSHIP_KEYWORDS):
        return None

    dataset = _find_mentioned_dataset(datasets, normalized_query)

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
    normalized_query: str,
) -> dict | None:

    if not any(keyword in normalized_query for keyword in LINEAGE_KEYWORDS):
        return None

    dataset = _find_mentioned_dataset(datasets, normalized_query)

    if dataset is None:
        return {
            "answer": (
                "I can answer lineage questions once you name a specific dataset - "
                "try something like \"what's downstream of orders\"."
            ),
            "sources": [],
        }

    upstream_edges = (
        db.query(DatasetLineage)
        .filter(DatasetLineage.downstream_dataset_id == dataset.id)
        .all()
    )

    downstream_edges = (
        db.query(DatasetLineage)
        .filter(DatasetLineage.upstream_dataset_id == dataset.id)
        .all()
    )

    dataset_by_id = {d.id: d for d in datasets}

    def _label(dataset_id):
        found = dataset_by_id.get(dataset_id)
        return f"{found.schema_name}.{found.name}" if found else dataset_id

    lines = []

    if upstream_edges:
        lines.append(
            "Depends on (upstream): "
            + ", ".join(_label(e.upstream_dataset_id) for e in upstream_edges)
        )

    if downstream_edges:
        lines.append(
            "Would be affected (downstream): "
            + ", ".join(_label(e.downstream_dataset_id) for e in downstream_edges)
        )

    if not lines:
        lines.append("No lineage relationships are recorded for this dataset yet.")

    sources = [
        {"type": "dataset", "id": dataset.id, "label": f"{dataset.schema_name}.{dataset.name}"}
    ]
    sources += [
        {"type": "dataset", "id": e.upstream_dataset_id, "label": _label(e.upstream_dataset_id)}
        for e in upstream_edges
    ]
    sources += [
        {"type": "dataset", "id": e.downstream_dataset_id, "label": _label(e.downstream_dataset_id)}
        for e in downstream_edges
    ]

    return {
        "answer": f"{dataset.schema_name}.{dataset.name}\n" + "\n".join(lines),
        "sources": sources,
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

    # Same scoping as _build_llm_context above - the snippet logic
    # right below only knows dataset/glossary_term shapes.
    results = semantic_search(
        db, organization_id, query,
        top_k=5,
        doc_types=("dataset", "glossary_term"),
    )

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

        if doc.doc_type == "dataset":
            snippet = doc.ref.description or doc.ref.ai_summary or ""
        else:
            snippet = doc.ref.definition or ""

        snippet = snippet.strip()[:140]

        lines.append(f"- {doc.label}: {snippet}" if snippet else f"- {doc.label}")
        sources.append({"type": doc.doc_type, "id": doc.id, "label": doc.label})

    answer = "Here's what I found related to your question:\n" + "\n".join(lines)

    return {"answer": answer, "sources": sources}


def answer_question(
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

    result = _answer_pii_question(datasets, normalized_query)
    if result is not None:
        return result

    result = _answer_ownership_question(datasets, normalized_query)
    if result is not None:
        return result

    result = _answer_lineage_question(db, datasets, normalized_query)
    if result is not None:
        return result

    result = _answer_governance_question(db, organization_id, normalized_query)
    if result is not None:
        return result

    result = _answer_contract_question(datasets, normalized_query)
    if result is not None:
        return result

    return _answer_via_semantic_search(db, organization_id, query)
