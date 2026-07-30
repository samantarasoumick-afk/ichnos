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
from app.services.onboarding_service import UnknownMilestoneError
from app.services.onboarding_service import get_progress
from app.services.onboarding_service import record_milestone


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


@router.get("/onboarding/progress")
def get_onboarding_progress(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    This user's progress through the Ecosystem View's onboarding
    milestones - what makes the "10 days instead of 3 months" claim
    measurable rather than asserted: real actions taken (viewed the
    map, explored each tier, traced a report's provenance, used
    semantic search), and once all of them are hit, the actual number
    of calendar days that took (see onboarding_service.get_progress).
    """

    return get_progress(db, current_user)


@router.post("/onboarding/milestones/{milestone_key}")
def record_onboarding_milestone(
    milestone_key: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Records that this user has hit a given onboarding milestone -
    idempotent, so the frontend can fire this every time the
    corresponding action happens (open the map, expand a front-office
    node, run a trace, run a search) without worrying about double-
    counting. Returns the updated progress summary.
    """

    try:
        record_milestone(db, current_user, milestone_key)
    except UnknownMilestoneError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

    return get_progress(db, current_user)
