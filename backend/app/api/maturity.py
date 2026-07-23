from fastapi import APIRouter
from fastapi import Depends

from sqlalchemy.orm import Session

from app.db.session import get_db

from app.models.user import User

from app.schemas.maturity import MaturityOverview

from app.auth.dependencies import get_current_user
from app.services.maturity_service import compute_maturity


router = APIRouter(
    prefix="/api/maturity",
    tags=["maturity"]
)


@router.get(
    "",
    response_model=MaturityOverview
)
@router.get(
    "/",
    response_model=MaturityOverview
)
def get_maturity_overview(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):

    return compute_maturity(db, current_user.organization_id)
