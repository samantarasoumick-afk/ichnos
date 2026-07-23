from collections import defaultdict

from fastapi import APIRouter
from fastapi import Depends

from sqlalchemy.orm import Session

from app.db.session import get_db

from app.models.dataset import Dataset
from app.models.column import DatasetColumn
from app.models.user import User

from app.auth.dependencies import get_current_user


router = APIRouter(
    prefix="/api/privacy",
    tags=["privacy"]
)


@router.get("/overview")
def privacy_overview(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):

    datasets = (
        db.query(Dataset)
        .filter(Dataset.organization_id == current_user.organization_id)
        .all()
    )

    total_datasets = len(datasets)

    average_privacy_score = 0

    if datasets:
        average_privacy_score = int(
            sum(dataset.privacy_score for dataset in datasets) / total_datasets
        )

    datasets_needing_consent_review = [
        dataset for dataset in datasets
        if any(c.consent_required for c in dataset.columns)
        and dataset.consent_status == "NOT_ASSESSED"
    ]

    datasets_overdue_retention = [
        dataset for dataset in datasets
        if dataset.retention_status == "OVERDUE"
    ]

    datasets_missing_purpose = [
        dataset for dataset in datasets
        if any(c.consent_required for c in dataset.columns) and not dataset.purpose
    ]

    columns = (
        db.query(DatasetColumn)
        .join(Dataset, DatasetColumn.dataset_id == Dataset.id)
        .filter(Dataset.organization_id == current_user.organization_id)
        .all()
    )

    dpdp_category_counts = defaultdict(int)
    for column in columns:
        if column.dpdp_category:
            dpdp_category_counts[column.dpdp_category] += 1

    top_at_risk = sorted(
        datasets,
        key=lambda d: d.privacy_score
    )[:5]

    return {
        "total_datasets": total_datasets,
        "average_privacy_score": average_privacy_score,
        "datasets_needing_consent_review": len(datasets_needing_consent_review),
        "datasets_overdue_retention": len(datasets_overdue_retention),
        "datasets_missing_purpose": len(datasets_missing_purpose),
        "sensitive_columns_by_dpdp_category": dict(dpdp_category_counts),
        "top_at_risk_datasets": [
            {
                "id": str(d.id),
                "name": d.name,
                "schema_name": d.schema_name,
                "privacy_score": d.privacy_score,
                "consent_status": d.consent_status,
                "retention_status": d.retention_status,
            }
            for d in top_at_risk
        ],
    }
