from datetime import datetime

from fastapi import APIRouter
from fastapi import Depends
from fastapi import HTTPException

from sqlalchemy.orm import Session

from app.db.session import get_db

from app.models.control import Control
from app.models.risk import RiskControlLink
from app.models.user import User

from app.schemas.control import ControlCreate
from app.schemas.control import ControlResponse
from app.schemas.control import ControlUpdate

from app.auth.dependencies import get_current_user
from app.auth.dependencies import require_role
from app.services.audit_service import log_audit_event


router = APIRouter(
    prefix="/api/controls",
    tags=["controls"]
)

VALID_CONTROL_TYPES = ("PREVENTIVE", "DETECTIVE", "CORRECTIVE")
VALID_CONTROL_STATUSES = ("EFFECTIVE", "INEFFECTIVE", "NOT_TESTED")


def _risk_count(db: Session, control_id: str) -> int:

    return (
        db.query(RiskControlLink)
        .filter(RiskControlLink.control_id == control_id)
        .count()
    )


def _email(db: Session, user_id: str) -> str | None:

    if not user_id:
        return None

    user = db.query(User).filter(User.id == user_id).first()

    return user.email if user else None


def _to_response(db: Session, control: Control) -> ControlResponse:

    return ControlResponse(
        id=control.id,
        name=control.name,
        description=control.description,
        control_type=control.control_type,
        status=control.status,
        owner_user_id=control.owner_user_id,
        owner_email=_email(db, control.owner_user_id),
        last_tested_at=control.last_tested_at,
        risk_count=_risk_count(db, control.id),
        created_at=control.created_at,
        updated_at=control.updated_at,
    )


def _get_control_or_404(control_id: str, db: Session, current_user: User) -> Control:

    control = (
        db.query(Control)
        .filter(
            Control.id == control_id,
            Control.organization_id == current_user.organization_id
        )
        .first()
    )

    if not control:
        raise HTTPException(status_code=404, detail="Control not found")

    return control


def _validate_owner(db: Session, owner_user_id, current_user: User):

    if not owner_user_id:
        return

    owner = (
        db.query(User)
        .filter(
            User.id == str(owner_user_id),
            User.organization_id == current_user.organization_id
        )
        .first()
    )

    if not owner:
        raise HTTPException(status_code=404, detail="Control owner not found in your organization")


@router.get(
    "",
    response_model=list[ControlResponse]
)
@router.get(
    "/",
    response_model=list[ControlResponse]
)
def list_controls(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):

    controls = (
        db.query(Control)
        .filter(Control.organization_id == current_user.organization_id)
        .order_by(Control.name)
        .all()
    )

    return [_to_response(db, control) for control in controls]


@router.post(
    "",
    response_model=ControlResponse
)
@router.post(
    "/",
    response_model=ControlResponse
)
def create_control(
    payload: ControlCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin", "steward"))
):

    control_type = payload.control_type.upper()

    if control_type not in VALID_CONTROL_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"control_type must be one of {VALID_CONTROL_TYPES}"
        )

    _validate_owner(db, payload.owner_user_id, current_user)

    control = Control(
        organization_id=current_user.organization_id,
        name=payload.name,
        description=payload.description,
        control_type=control_type,
        status="NOT_TESTED",
        owner_user_id=str(payload.owner_user_id) if payload.owner_user_id else None,
        created_by=current_user.id,
    )

    db.add(control)
    db.flush()

    log_audit_event(
        db,
        organization_id=current_user.organization_id,
        action="control.create",
        actor_user_id=current_user.id,
        actor_email=current_user.email,
        resource_type="control",
        resource_id=control.id,
        details=f"Created control '{control.name}'",
    )

    db.commit()
    db.refresh(control)

    return _to_response(db, control)


@router.patch(
    "/{control_id}",
    response_model=ControlResponse
)
def update_control(
    control_id: str,
    payload: ControlUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin", "steward"))
):

    control = _get_control_or_404(control_id, db, current_user)

    updates = payload.model_dump(exclude_unset=True, exclude={"mark_tested_now"})

    if "control_type" in updates and updates["control_type"]:
        control_type = updates["control_type"].upper()
        if control_type not in VALID_CONTROL_TYPES:
            raise HTTPException(
                status_code=400,
                detail=f"control_type must be one of {VALID_CONTROL_TYPES}"
            )
        updates["control_type"] = control_type

    if "status" in updates and updates["status"]:
        status = updates["status"].upper()
        if status not in VALID_CONTROL_STATUSES:
            raise HTTPException(
                status_code=400,
                detail=f"status must be one of {VALID_CONTROL_STATUSES}"
            )
        updates["status"] = status

    if "owner_user_id" in updates:
        _validate_owner(db, updates["owner_user_id"], current_user)
        updates["owner_user_id"] = str(updates["owner_user_id"]) if updates["owner_user_id"] else None

    for field, value in updates.items():
        setattr(control, field, value)

    if payload.mark_tested_now:
        control.last_tested_at = datetime.utcnow()

    log_audit_event(
        db,
        organization_id=current_user.organization_id,
        action="control.update",
        actor_user_id=current_user.id,
        actor_email=current_user.email,
        resource_type="control",
        resource_id=control.id,
        details=f"Updated control '{control.name}': {', '.join(updates.keys()) or 'tested'}",
    )

    db.commit()
    db.refresh(control)

    return _to_response(db, control)


@router.delete("/{control_id}")
def delete_control(
    control_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin", "steward"))
):

    control = _get_control_or_404(control_id, db, current_user)

    db.query(RiskControlLink).filter(
        RiskControlLink.control_id == control.id
    ).delete(synchronize_session=False)

    db.delete(control)

    log_audit_event(
        db,
        organization_id=current_user.organization_id,
        action="control.delete",
        actor_user_id=current_user.id,
        actor_email=current_user.email,
        resource_type="control",
        resource_id=control_id,
        details=f"Deleted control '{control.name}'",
    )

    db.commit()

    return {"message": "Control deleted"}
