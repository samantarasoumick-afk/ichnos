"""
Natural-language Q&A over the catalog. No LLM is wired in today -
every question is answered by one of two deterministic paths:

  1. Intent detection: a handful of common governance questions (PII
     exposure, ownership, lineage, governance/maturity standing,
     contract health) are recognized by keyword and answered directly
     from real data via a template - these are the "simple" questions
     and the answers are exact, not generated.
  2. Semantic fallback: anything that doesn't match a known intent
     falls back to catalog_search_service's TF-IDF retrieval and
     returns the closest-matching datasets/glossary terms.

_try_llm_answer is the pluggable seam for genuine open-ended
answering later: it checks for an API key today, finds none, and
returns None - so answer_question() always continues to the
deterministic paths above. Wiring a real LLM call in later (using the
same retrieved context this module already assembles) doesn't require
changing anything else in this file or its callers.
"""

import os

from sqlalchemy.orm import Session

from app.models.dataset import Dataset
from app.models.lineage import DatasetLineage

from app.services.catalog_search_service import semantic_search
from app.services.maturity_service import compute_maturity


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


def _try_llm_answer(query: str, context: str) -> dict | None:
    """
    Seam for a real LLM-backed answer. Returns None today (no API key
    configured), which sends every question through the deterministic
    paths below instead. To upgrade: check for e.g. ANTHROPIC_API_KEY,
    call the API with `query` and `context` (already-retrieved
    grounding text), and return {"answer": ..., "sources": [...]}. No
    other function in this module needs to change.
    """

    if not os.getenv("ANTHROPIC_API_KEY"):
        return None

    # Real implementation goes here once a key is configured.
    return None


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

        if doc.doc_type == "dataset":
            snippet = doc.ref.description or doc.ref.ai_summary or ""
        else:
            snippet = doc.ref.definition or ""

        snippet = snippet.strip()[:140]

        lines.append(f"- {doc.label}: {snippet}" if snippet else f"- {doc.label}")
        sources.append({"type": doc.doc_type, "id": doc.id, "label": doc.label})

    answer = "Here's what I found related to your question:\n" + "\n".join(lines)

    return {"answer": answer, "sources": sources}


def answer_question(db: Session, organization_id: str, query: str) -> dict:

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

    llm_answer = _try_llm_answer(query, context="")
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
