from fastapi import APIRouter
from fastapi import Depends
from fastapi import HTTPException

from sqlalchemy.orm import Session

from app.db.session import get_db

from app.models.source import DataSource
from app.models.user import User

from app.auth.dependencies import get_current_user
from app.auth.dependencies import require_role

from app.services.demo_data_service import (
    DemoDataAlreadyLoadedError,
    clear_demo_data,
    seed_demo_data,
)


router = APIRouter(
    prefix="/api/demo",
    tags=["demo"]
)


@router.get("/status")
def demo_status(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Whether this organization currently has demo data loaded, and how
    many sources it accounts for - enough for the frontend to decide
    whether to show "Load Demo Data" or "Clear Demo Data".
    """

    count = (
        db.query(DataSource)
        .filter(
            DataSource.organization_id == current_user.organization_id,
            DataSource.is_seed_data.is_(True),
        )
        .count()
    )

    return {
        "demo_data_loaded": count > 0,
        "demo_source_count": count,
    }


@router.post("/seed")
def seed_demo(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin", "steward"))
):
    """
    Populates this organization's catalog with a full, connected demo
    estate - three front-office applications feeding a dbt-modeled
    warehouse feeding Tableau reporting - so every feature (lineage,
    column-level lineage, data quality, contracts, governance status,
    certification, discussions, risks & controls, privacy fields,
    team roles, and search/Ask activity) can be seen working together
    instead of one at a time on hand-picked sample rows. See
    demo_data_service.py for the full narrative.
    """

    try:
        summary = seed_demo_data(db, current_user)
    except DemoDataAlreadyLoadedError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    return {
        "message": "Demo data loaded successfully",
        **summary,
    }


@router.post("/clear")
def clear_demo(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin", "steward"))
):
    """
    Removes every source, dataset, and dependent record the demo
    seeder created for this organization - identified purely by the
    is_seed_data flag, so anything a real user connected or uploaded
    (even something that happens to share a name with a demo source)
    is left untouched.
    """

    summary = clear_demo_data(
        db,
        current_user.organization_id,
        actor_user_id=current_user.id,
        actor_email=current_user.email,
    )

    return {
        "message": "Demo data cleared successfully",
        **summary,
    }
