"""
Rolls up per-dataset signals that already exist (governance_score,
privacy_score, quality_score, active_contract) into one org-level
"how mature is this org's data governance" score and named level -
the discovery-phase framing the platform is missing today: a brand
new org staring at an empty catalog, or an established one wondering
whether they're actually making progress, both need one number and a
short list of what to do next, not six separate dashboards to piece
together themselves.

Deliberately pure aggregation - no new tables, nothing this can get
out of sync with, since it's computed live from Dataset (and its
already-computed properties) plus DataContract every time it's asked
for.
"""

from sqlalchemy.orm import Session

from app.models.dataset import Dataset


# Below this coverage fraction on a dimension, it's worth calling out
# as a recommended next step - chosen loosely, not from a formal
# study: below 60% coverage is "most datasets are missing this",
# which reads as an actionable gap rather than noise.
RECOMMENDATION_THRESHOLD = 0.6

# dataset_ingestion_service.py sets this as a placeholder steward at
# creation time (same idea as owner="SYSTEM") so nothing is ever
# blank - but that means Dataset.steward being non-empty doesn't mean
# a real person has actually taken ownership. Treat the placeholder
# the same as "unassigned" for maturity purposes, or every dataset
# would trivially show 100% steward coverage on day one.
PLACEHOLDER_STEWARD = "DATA_TEAM"


def compute_maturity(db: Session, organization_id: str) -> dict:

    datasets = (
        db.query(Dataset)
        .filter(Dataset.organization_id == organization_id)
        .all()
    )

    total = len(datasets)

    if total == 0:

        return {
            "total_datasets": 0,
            "level": "NOT_STARTED",
            "overall_score": 0,
            "coverage": {
                "pct_with_steward": 0,
                "pct_certified": 0,
                "pct_with_active_contract": 0,
                "pct_pii_with_documented_purpose": 0,
            },
            "average_scores": {
                "governance_score": 0,
                "privacy_score": 0,
                "quality_score": 0,
            },
            "recommended_next_steps": [
                "Connect your first data source, or upload a CSV, to start building your catalog."
            ],
        }

    with_steward = sum(
        1 for d in datasets
        if d.steward and d.steward != PLACEHOLDER_STEWARD
    )
    certified = sum(1 for d in datasets if d.certification == "VERIFIED")
    with_active_contract = sum(1 for d in datasets if d.active_contract is not None)

    # Only datasets that actually carry meaningful personal data are
    # judged on whether a purpose is documented - same philosophy as
    # Dataset.privacy_score not penalizing datasets with nothing
    # sensitive in them.
    pii_bearing = [d for d in datasets if d.sensitivity_score in ("MEDIUM", "HIGH")]
    pii_with_purpose = sum(1 for d in pii_bearing if d.purpose)

    pct_with_steward = with_steward / total
    pct_certified = certified / total
    pct_with_active_contract = with_active_contract / total
    pct_pii_with_purpose = (
        (pii_with_purpose / len(pii_bearing)) if pii_bearing else 1.0
    )

    avg_governance = sum(d.governance_score for d in datasets) / total
    avg_privacy = sum(d.privacy_score for d in datasets) / total
    avg_quality = sum(d.quality_score for d in datasets) / total

    coverage_score = 100 * (
        pct_with_steward
        + pct_certified
        + pct_with_active_contract
        + pct_pii_with_purpose
    ) / 4

    overall_score = round(
        (coverage_score + avg_governance + avg_privacy + avg_quality) / 4
    )

    if overall_score >= 75:
        level = "TRUSTED"
    elif overall_score >= 50:
        level = "MANAGED"
    elif overall_score >= 25:
        level = "REACTIVE"
    else:
        level = "AD_HOC"

    candidate_recommendations = [
        (
            pct_with_steward,
            f"Assign a steward to your {total - with_steward} unowned dataset(s)."
        ),
        (
            pct_certified,
            f"Certify your highest-value or highest-risk datasets "
            f"({certified}/{total} currently VERIFIED)."
        ),
        (
            pct_with_active_contract,
            f"Define a data contract for your critical tables "
            f"({with_active_contract}/{total} currently under an active contract)."
        ),
    ]

    if pii_bearing:
        candidate_recommendations.append((
            pct_pii_with_purpose,
            f"Document a purpose for your {len(pii_bearing) - pii_with_purpose} "
            f"PII-bearing dataset(s) that are missing one."
        ))

    weakest_first = sorted(
        (item for item in candidate_recommendations if item[0] < RECOMMENDATION_THRESHOLD),
        key=lambda item: item[0]
    )

    recommended_next_steps = [message for _pct, message in weakest_first[:3]]

    if not recommended_next_steps:
        recommended_next_steps = [
            "Governance coverage looks strong across the board - keep certifying "
            "and contracting new datasets as they're discovered."
        ]

    return {
        "total_datasets": total,
        "level": level,
        "overall_score": overall_score,
        "coverage": {
            "pct_with_steward": round(pct_with_steward * 100),
            "pct_certified": round(pct_certified * 100),
            "pct_with_active_contract": round(pct_with_active_contract * 100),
            "pct_pii_with_documented_purpose": round(pct_pii_with_purpose * 100),
        },
        "average_scores": {
            "governance_score": round(avg_governance),
            "privacy_score": round(avg_privacy),
            "quality_score": round(avg_quality),
        },
        "recommended_next_steps": recommended_next_steps,
    }
