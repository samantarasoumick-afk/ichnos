from fastapi import APIRouter
from fastapi import Depends

from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.dataset import Dataset
from app.models.user import User

from app.auth.dependencies import get_current_user

router = APIRouter(
    prefix="/api/dashboard",
    tags=["dashboard"]
)


@router.get("/overview")
def dashboard_overview(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):

    datasets = (
        db.query(Dataset)
        .filter(Dataset.organization_id == current_user.organization_id)
        .all()
    )

    total_datasets = len(datasets)

    critical = len([
        d for d in datasets
        if d.governance_status == "CRITICAL"
    ])

    stale = len([
        d for d in datasets
        if d.freshness_status == "STALE"
    ])

    avg_trust = 0

    if datasets:

        avg_trust = int(
            sum(d.trust_score for d in datasets)
            / len(datasets)
        )

    top_risky = sorted(
        datasets,
        key=lambda d: d.risk_score,
        reverse=True
    )[:5]

    return {
        "total_datasets": total_datasets,
        "critical_datasets": critical,
        "stale_datasets": stale,
        "average_trust_score": avg_trust,
        "top_risky_datasets": [
            {
                "id": str(d.id),
                "name": d.name,
                "schema_name": d.schema_name,
                "risk_score": d.risk_score,
                "trust_score": d.trust_score,
                "governance_status": d.governance_status,
            }
            for d in top_risky
        ]
    }
