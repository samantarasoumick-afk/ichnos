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
from app.services.guided_tour_service import (
    UnknownTourScenarioError,
    ensure_tour_step,
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


@router.post("/tour/{scenario_id}/step/{step_index}")
def ensure_tour_step_data(
    scenario_id: str,
    step_index: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin", "steward"))
):
    """
    Idempotently creates every piece of demo data a guided tour
    scenario needs up through (and including) the given step - called
    by the frontend tour stepper right before it navigates to that
    step, so the target dataset/contract/discussion/etc. actually
    exists by the time the page loads. Safe to call repeatedly
    (advancing, going back, or re-visiting a step): see
    guided_tour_service.py for why each step's data is idempotent.

    Unlike POST /demo/seed, this does not require the organization to
    be free of existing demo data - a guided tour can start from an
    empty catalog, build up incrementally as steps are taken, or run
    on top of an already-fully-seeded org (in which case every
    checkpoint just finds its data already present).
    """

    try:
        summary = ensure_tour_step(db, current_user, scenario_id, step_index)
    except UnknownTourScenarioError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except IndexError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    return summary


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
