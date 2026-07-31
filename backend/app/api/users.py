import json

from fastapi import APIRouter
from fastapi import Depends
from fastapi import HTTPException

from sqlalchemy.orm import Session

from app.db.session import get_db

from app.models.user import User

from app.schemas.user import DashboardMetricsResponse
from app.schemas.user import DashboardMetricsUpdate
from app.schemas.user import TeamMemberInvite
from app.schemas.user import TeamMemberResponse
from app.schemas.user import TeamMemberUpdate

from app.auth.security import hash_password
from app.auth.dependencies import get_current_user
from app.auth.dependencies import require_role
from app.services.audit_service import log_audit_event
from app.services.entitlements import enforce_seat_limit


router = APIRouter(
    prefix="/api/users",
    tags=["users"]
)

VALID_ROLES = {"admin", "steward", "data_owner", "viewer"}


def _other_active_admins(db: Session, organization_id: str, excluding_user_id: str) -> int:

    return (
        db.query(User)
        .filter(
            User.organization_id == organization_id,
            User.role == "admin",
            User.is_active.is_(True),
            User.id != excluding_user_id
        )
        .count()
    )


@router.get(
    "",
    response_model=list[TeamMemberResponse]
)
@router.get(
    "/",
    response_model=list[TeamMemberResponse]
)
def list_team_members(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):

    return (
        db.query(User)
        .filter(User.organization_id == current_user.organization_id)
        .order_by(User.created_at.asc())
        .all()
    )


@router.post(
    "",
    response_model=TeamMemberResponse
)
@router.post(
    "/",
    response_model=TeamMemberResponse
)
def invite_team_member(
    payload: TeamMemberInvite,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin"))
):

    if payload.role not in VALID_ROLES:

        raise HTTPException(
            status_code=400,
            detail=f"Role must be one of: {', '.join(sorted(VALID_ROLES))}"
        )

    # Viewer seats are free and unlimited on every plan - only
    # non-viewer ("editor") roles count against the seat cap.
    if payload.role != "viewer":
        enforce_seat_limit(db, current_user)

    existing_user = (
        db.query(User)
        .filter(User.email == payload.email)
        .first()
    )

    if existing_user:

        raise HTTPException(
            status_code=400,
            detail="A user with this email already exists"
        )

    new_user = User(
        email=payload.email,
        password_hash=hash_password(payload.password),
        role=payload.role,
        organization_id=current_user.organization_id,
        is_active=True
    )

    db.add(new_user)
    db.flush()

    log_audit_event(
        db,
        organization_id=current_user.organization_id,
        action="user.invite",
        actor_user_id=current_user.id,
        actor_email=current_user.email,
        resource_type="user",
        resource_id=new_user.id,
        details=f"Invited {new_user.email} as {new_user.role}",
    )

    db.commit()
    db.refresh(new_user)

    return new_user


@router.patch(
    "/{user_id}",
    response_model=TeamMemberResponse
)
def update_team_member(
    user_id: str,
    payload: TeamMemberUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin"))
):

    member = (
        db.query(User)
        .filter(
            User.id == user_id,
            User.organization_id == current_user.organization_id
        )
        .first()
    )

    if not member:

        raise HTTPException(
            status_code=404,
            detail="Team member not found"
        )

    updates = payload.model_dump(exclude_unset=True)

    if "role" in updates and updates["role"] not in VALID_ROLES:

        raise HTTPException(
            status_code=400,
            detail=f"Role must be one of: {', '.join(sorted(VALID_ROLES))}"
        )

    becoming_non_admin = "role" in updates and updates["role"] != "admin"
    becoming_inactive = "is_active" in updates and updates["is_active"] is False

    if member.role == "admin" and (becoming_non_admin or becoming_inactive):

        if _other_active_admins(db, current_user.organization_id, member.id) == 0:

            raise HTTPException(
                status_code=400,
                detail="Cannot remove the last active admin in the organization"
            )

    for field, value in updates.items():
        setattr(member, field, value)

    log_audit_event(
        db,
        organization_id=current_user.organization_id,
        action="user.update",
        actor_user_id=current_user.id,
        actor_email=current_user.email,
        resource_type="user",
        resource_id=member.id,
        details=f"Updated fields: {', '.join(updates.keys())}",
    )

    db.commit()
    db.refresh(member)

    return member


@router.get(
    "/me/dashboard-metrics",
    response_model=DashboardMetricsResponse
)
def get_my_dashboard_metrics(
    current_user: User = Depends(get_current_user)
):
    """
    The current user's chosen home-dashboard KPI cards. `metrics: null`
    means no preference has been saved yet - the frontend falls back
    to its own default set rather than treating this as "show nothing."
    """

    if not current_user.dashboard_metrics:

        return DashboardMetricsResponse(metrics=None)

    try:

        metrics = json.loads(current_user.dashboard_metrics)

    except (TypeError, ValueError):

        metrics = None

    return DashboardMetricsResponse(metrics=metrics)


@router.put(
    "/me/dashboard-metrics",
    response_model=DashboardMetricsResponse
)
def update_my_dashboard_metrics(
    payload: DashboardMetricsUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Every user picks their own dashboard - no role restriction here,
    unlike most other settings in this file. This only ever touches
    the calling user's own row (current_user, not a user_id path
    param), so there's nothing to authorize beyond being logged in.
    """

    current_user.dashboard_metrics = json.dumps(payload.metrics)

    db.commit()
    db.refresh(current_user)

    return DashboardMetricsResponse(metrics=payload.metrics)
