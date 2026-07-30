from fastapi import APIRouter
from fastapi import Depends

from sqlalchemy.orm import Session

from app.db.session import get_db

from app.models.user import User

from app.auth.dependencies import get_current_user

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
