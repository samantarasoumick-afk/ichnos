from fastapi import APIRouter
from fastapi import Depends
from fastapi import HTTPException
from fastapi import Query

from sqlalchemy.orm import Session

from app.db.session import get_db

from app.models.user import User

from app.auth.dependencies import get_current_user

from app.services.dashboard_trace_service import DatasetNotFoundError
from app.services.dashboard_trace_service import DIRECTION_DOWNSTREAM
from app.services.dashboard_trace_service import DIRECTION_UPSTREAM
from app.services.dashboard_trace_service import build_trace
from app.services.ecosystem_service import build_ecosystem_graph


router = APIRouter(
    prefix="/api/ecosystem",
    tags=["ecosystem"]
)


@router.get("")
@router.get("/")
def get_ecosystem_graph(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    The whole data estate as one map: sources as top-level nodes
    (rolled up dataset/column/PII counts), each source's individual
    datasets, and the lineage edges connecting them - tiered into
    front/middle/back office purely from the real lineage graph's
    topology (see ecosystem_service.py). Any authenticated role can
    view this - it's an onboarding aid, not a governance action.
    """

    return build_ecosystem_graph(db, current_user.organization_id)


@router.get("/trace/{dataset_id}")
def trace_dataset(
    dataset_id: str,
    direction: str = Query(default=DIRECTION_UPSTREAM, pattern=f"^({DIRECTION_UPSTREAM}|{DIRECTION_DOWNSTREAM})$"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    "Trace this dashboard": walks the real lineage graph hop by hop
    from `dataset_id` - upstream (default) to explain where a report's
    numbers actually came from, or downstream to explain everything a
    raw table feeds - and returns both the structured hop-by-hop trace
    and a plain-English narrative (LLM-assisted when ANTHROPIC_API_KEY
    is set, a deterministic template otherwise; see
    dashboard_trace_service.py).
    """

    try:
        return build_trace(db, current_user.organization_id, dataset_id, direction=direction)
    except DatasetNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
