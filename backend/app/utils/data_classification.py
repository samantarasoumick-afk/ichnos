"""
Heuristic auto-classification of a dataset into one of four data
categories - the same conceptual split most data-management
frameworks use:

MASTER: core business entities (customers, products, employees,
    accounts, vendors) - the "who/what" everything else refers to.
REFERENCE: small, mostly-static lookup/code data (country codes,
    currencies, statuses, categories) - the controlled vocabularies
    other datasets point into.
TRANSACTIONAL: operational events and records (orders, payments,
    tickets, sessions) - the "what happened" data, usually
    high-volume and append-heavy.
ANALYTICAL: derived/aggregated data built for reporting or BI
    (dashboards, marts, summaries, fact tables) - downstream of the
    other three.

This is a naming/shape heuristic, not a data-profiling one - it runs
once at dataset creation (see dataset_ingestion_service.py) when no
row-level statistics are available yet. A steward can always
override the result afterward via the governance-update endpoint, so
a wrong guess here is never permanent.
"""

MASTER_KEYWORDS = [
    "customer", "client", "product", "employee", "staff", "vendor",
    "supplier", "account", "user", "member", "party", "parties",
    "company", "companies", "organization", "patient", "contact",
    "asset", "device",
]

REFERENCE_KEYWORDS = [
    "lookup", "ref_", "_ref", "reference", "code", "codes", "type",
    "types", "category", "categories", "country", "currency",
    "status", "config", "dictionary", "taxonomy", "region", "zone",
]

TRANSACTIONAL_KEYWORDS = [
    "order", "transaction", "payment", "invoice", "event", "log",
    "click", "session", "booking", "shipment", "claim", "ticket",
    "lead", "opportunity", "opportunities", "interaction",
    "activity", "activities", "usage",
]

ANALYTICAL_KEYWORDS = [
    "summary", "agg", "aggregate", "report", "dashboard", "metrics",
    "warehouse", "mart", "analytics", "kpi", "fact_", "fct_", "dim_",
    "insight", "forecast",
]

# Columns that, on their own, nudge a dataset toward ANALYTICAL even
# if the name is ambiguous - pre-computed totals/rates/scores are a
# strong signal of derived, reporting-oriented data.
ANALYTICAL_COLUMN_HINTS = [
    "total", "avg", "average", "rate", "score", "pct", "percent",
    "count", "sum",
]


def classify_data_category(
    schema_name: str,
    table_name: str,
    column_names: list[str],
) -> str:
    """
    Returns one of "MASTER", "REFERENCE", "TRANSACTIONAL",
    "ANALYTICAL". Falls back to "TRANSACTIONAL" when nothing matches,
    since day-to-day operational records are the most common
    unclassified case in a typical catalog.
    """

    text = f"{schema_name or ''} {table_name or ''}".lower()

    columns_text = " ".join(
        (name or "").lower() for name in column_names
    )

    scores = {
        "MASTER": sum(1 for kw in MASTER_KEYWORDS if kw in text),
        "REFERENCE": sum(1 for kw in REFERENCE_KEYWORDS if kw in text),
        "TRANSACTIONAL": sum(1 for kw in TRANSACTIONAL_KEYWORDS if kw in text),
        "ANALYTICAL": sum(1 for kw in ANALYTICAL_KEYWORDS if kw in text),
    }

    scores["ANALYTICAL"] += sum(
        1 for hint in ANALYTICAL_COLUMN_HINTS if hint in columns_text
    )

    # A small table (few columns, name matches a reference keyword)
    # is a stronger reference-data signal than a large one - lookup
    # tables are typically narrow (code + label + maybe a couple of
    # descriptive fields).
    if scores["REFERENCE"] > 0 and len(column_names) <= 5:
        scores["REFERENCE"] += 1

    best_category = max(scores, key=scores.get)

    if scores[best_category] == 0:
        return "TRANSACTIONAL"

    return best_category
