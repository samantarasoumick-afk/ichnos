from typing import Optional

from fastapi import APIRouter
from fastapi import Depends
from fastapi import HTTPException

from sqlalchemy.orm import Session

from app.db.session import get_db

from app.models.business_process import BusinessProcess
from app.models.control import Control
from app.models.dataset import Dataset
from app.models.risk import Risk
from app.models.risk import RiskControlLink
from app.models.risk import RiskDatasetLink
from app.models.risk import RiskProcessLink
from app.models.user import User

from app.schemas.risk import RiskCreate
from app.schemas.risk import RiskControlLinkCreate
from app.schemas.risk import RiskDatasetLinkCreate
from app.schemas.risk import RiskDetailResponse
from app.schemas.risk import RiskLinkedControl
from app.schemas.risk import RiskLinkedDataset
from app.schemas.risk import RiskLinkedProcess
from app.schemas.risk import RiskProcessLinkCreate
from app.schemas.risk import RiskResponse
from app.schemas.risk import RiskUpdate

from app.auth.dependencies import get_current_user
from app.auth.dependencies import require_role
from app.services.audit_service import log_audit_event
from app.services.risk_scoring import compute_risk_scores


router = APIRouter(
    prefix="/api/risks",
    tags=["risks"]
)

VALID_CATEGORIES = ("PRIVACY", "SECURITY", "OPERATIONAL", "COMPLIANCE", "DATA_QUALITY", "OTHER")
VALID_LEVELS = ("LOW", "MEDIUM", "HIGH")
VALID_STATUSES = ("OPEN", "MITIGATED", "ACCEPTED", "CLOSED")


def _email(db: Session, user_id: Optional[str]) -> Optional[str]:

    if not user_id:
        return None

    user = db.query(User).filter(User.id == user_id).first()

    return user.email if user else None


def _effective_control_count(db: Session, risk_id: str) -> int:

    return (
        db.query(RiskControlLink)
        .join(Control, Control.id == RiskControlLink.control_id)
        .filter(
            RiskControlLink.risk_id == risk_id,
            Control.status == "EFFECTIVE"
        )
        .count()
    )


def _counts(db: Session, risk_id: str) -> dict:

    return {
        "dataset_count": db.query(RiskDatasetLink).filter(RiskDatasetLink.risk_id == risk_id).count(),
        "process_count": db.query(RiskProcessLink).filter(RiskProcessLink.risk_id == risk_id).count(),
        "control_count": db.query(RiskControlLink).filter(RiskControlLink.risk_id == risk_id).count(),
    }


def _to_response(db: Session, risk: Risk) -> RiskResponse:

    effective = _effective_control_count(db, risk.id)
    scores = compute_risk_scores(risk.likelihood, risk.impact, effective)
    counts = _counts(db, risk.id)

    return RiskResponse(
        id=risk.id,
        title=risk.title,
        description=risk.description,
        category=risk.category,
        likelihood=risk.likelihood,
        impact=risk.impact,
        status=risk.status,
        owner_user_id=risk.owner_user_id,
        owner_email=_email(db, risk.owner_user_id),
        created_by=risk.created_by,
        created_by_email=_email(db, risk.created_by),
        effective_control_count=effective,
        created_at=risk.created_at,
        updated_at=risk.updated_at,
        **scores,
        **counts,
    )


def _to_detail_response(db: Session, risk: Risk) -> RiskDetailResponse:

    base = _to_response(db, risk)

    linked_datasets = (
        db.query(Dataset)
        .join(RiskDatasetLink, RiskDatasetLink.dataset_id == Dataset.id)
        .filter(RiskDatasetLink.risk_id == risk.id)
        .all()
    )

    linked_processes = (
        db.query(BusinessProcess)
        .join(RiskProcessLink, RiskProcessLink.process_id == BusinessProcess.id)
        .filter(RiskProcessLink.risk_id == risk.id)
        .all()
    )

    linked_controls = (
        db.query(Control)
        .join(RiskControlLink, RiskControlLink.control_id == Control.id)
        .filter(RiskControlLink.risk_id == risk.id)
        .all()
    )

    return RiskDetailResponse(
        **base.model_dump(),
        linked_datasets=[
            RiskLinkedDataset(id=d.id, name=d.name, schema_name=d.schema_name)
            for d in linked_datasets
        ],
        linked_processes=[
            RiskLinkedProcess(id=p.id, name=p.name) for p in linked_processes
        ],
        linked_controls=[
            RiskLinkedControl(id=c.id, name=c.name, status=c.status) for c in linked_controls
        ],
    )


def _get_risk_or_404(risk_id: str, db: Session, current_user: User) -> Risk:

    risk = (
        db.query(Risk)
        .filter(
            Risk.id == risk_id,
            Risk.organization_id == current_user.organization_id
        )
        .first()
    )

    if not risk:
        raise HTTPException(status_code=404, detail="Risk not found")

    return risk


def _get_dataset_or_404(dataset_id: str, db: Session, current_user: User) -> Dataset:

    dataset = (
        db.query(Dataset)
        .filter(
            Dataset.id == dataset_id,
            Dataset.organization_id == current_user.organization_id
        )
        .first()
    )

    if not dataset:
        raise HTTPException(status_code=404, detail="Dataset not found")

    return dataset


def _get_process_or_404(process_id: str, db: Session, current_user: User) -> BusinessProcess:

    process = (
        db.query(BusinessProcess)
        .filter(
            BusinessProcess.id == process_id,
            BusinessProcess.organization_id == current_user.organization_id
        )
        .first()
    )

    if not process:
        raise HTTPException(status_code=404, detail="Business process not found")

    return process


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
        raise HTTPException(status_code=404, detail="Risk owner not found in your organization")


@router.get(
    "",
    response_model=list[RiskResponse]
)
@router.get(
    "/",
    response_model=list[RiskResponse]
)
def list_risks(
    status: Optional[str] = None,
    category: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):

    query = db.query(Risk).filter(Risk.organization_id == current_user.organization_id)

    if status:
        query = query.filter(Risk.status == status.upper())

    if category:
        query = query.filter(Risk.category == category.upper())

    risks = query.order_by(Risk.created_at.desc()).all()

    return [_to_response(db, risk) for risk in risks]


@router.post(
    "",
    response_model=RiskDetailResponse
)
@router.post(
    "/",
    response_model=RiskDetailResponse
)
def create_risk(
    payload: RiskCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin", "steward"))
):

    category = payload.category.upper()
    likelihood = payload.likelihood.upper()
    impact = payload.impact.upper()

    if category not in VALID_CATEGORIES:
        raise HTTPException(status_code=400, detail=f"category must be one of {VALID_CATEGORIES}")

    if likelihood not in VALID_LEVELS or impact not in VALID_LEVELS:
        raise HTTPException(status_code=400, detail=f"likelihood/impact must be one of {VALID_LEVELS}")

    _validate_owner(db, payload.owner_user_id, current_user)

    risk = Risk(
        organization_id=current_user.organization_id,
        title=payload.title,
        description=payload.description,
        category=category,
        likelihood=likelihood,
        impact=impact,
        status="OPEN",
        owner_user_id=str(payload.owner_user_id) if payload.owner_user_id else None,
        created_by=current_user.id,
    )

    db.add(risk)
    db.flush()

    log_audit_event(
        db,
        organization_id=current_user.organization_id,
        action="risk.create",
        actor_user_id=current_user.id,
        actor_email=current_user.email,
        resource_type="risk",
        resource_id=risk.id,
        details=f"Opened risk '{risk.title}' ({category}, {likelihood} likelihood / {impact} impact)",
    )

    db.commit()
    db.refresh(risk)

    return _to_detail_response(db, risk)


@router.get(
    "/{risk_id}",
    response_model=RiskDetailResponse
)
def get_risk(
    risk_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):

    risk = _get_risk_or_404(risk_id, db, current_user)

    return _to_detail_response(db, risk)


@router.patch(
    "/{risk_id}",
    response_model=RiskDetailResponse
)
def update_risk(
    risk_id: str,
    payload: RiskUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin", "steward"))
):

    risk = _get_risk_or_404(risk_id, db, current_user)

    updates = payload.model_dump(exclude_unset=True)

    if "category" in updates and updates["category"]:
        category = updates["category"].upper()
        if category not in VALID_CATEGORIES:
            raise HTTPException(status_code=400, detail=f"category must be one of {VALID_CATEGORIES}")
        updates["category"] = category

    for level_field in ("likelihood", "impact"):
        if level_field in updates and updates[level_field]:
            level = updates[level_field].upper()
            if level not in VALID_LEVELS:
                raise HTTPException(status_code=400, detail=f"{level_field} must be one of {VALID_LEVELS}")
            updates[level_field] = level

    if "status" in updates and updates["status"]:
        status = updates["status"].upper()
        if status not in VALID_STATUSES:
            raise HTTPException(status_code=400, detail=f"status must be one of {VALID_STATUSES}")
        updates["status"] = status

    if "owner_user_id" in updates:
        _validate_owner(db, updates["owner_user_id"], current_user)
        updates["owner_user_id"] = str(updates["owner_user_id"]) if updates["owner_user_id"] else None

    for field, value in updates.items():
        setattr(risk, field, value)

    log_audit_event(
        db,
        organization_id=current_user.organization_id,
        action="risk.update",
        actor_user_id=current_user.id,
        actor_email=current_user.email,
        resource_type="risk",
        resource_id=risk.id,
        details=f"Updated risk '{risk.title}': {', '.join(updates.keys())}",
    )

    db.commit()
    db.refresh(risk)

    return _to_detail_response(db, risk)


@router.delete("/{risk_id}")
def delete_risk(
    risk_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin", "steward"))
):

    risk = _get_risk_or_404(risk_id, db, current_user)

    for link_model in (RiskDatasetLink, RiskProcessLink, RiskControlLink):
        db.query(link_model).filter(link_model.risk_id == risk.id).delete(synchronize_session=False)

    db.delete(risk)

    log_audit_event(
        db,
        organization_id=current_user.organization_id,
        action="risk.delete",
        actor_user_id=current_user.id,
        actor_email=current_user.email,
        resource_type="risk",
        resource_id=risk_id,
        details=f"Deleted risk '{risk.title}'",
    )

    db.commit()

    return {"message": "Risk deleted"}


@router.post(
    "/{risk_id}/datasets",
    response_model=RiskDetailResponse
)
def link_dataset(
    risk_id: str,
    payload: RiskDatasetLinkCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin", "steward"))
):

    risk = _get_risk_or_404(risk_id, db, current_user)
    dataset = _get_dataset_or_404(str(payload.dataset_id), db, current_user)

    existing = (
        db.query(RiskDatasetLink)
        .filter(RiskDatasetLink.risk_id == risk.id, RiskDatasetLink.dataset_id == dataset.id)
        .first()
    )

    if existing:
        raise HTTPException(status_code=400, detail="This dataset is already linked to that risk.")

    db.add(RiskDatasetLink(risk_id=risk.id, dataset_id=dataset.id))

    log_audit_event(
        db,
        organization_id=current_user.organization_id,
        action="risk.link_dataset",
        actor_user_id=current_user.id,
        actor_email=current_user.email,
        resource_type="risk",
        resource_id=risk.id,
        details=f"Linked risk '{risk.title}' to dataset '{dataset.schema_name}.{dataset.name}'",
    )

    db.commit()

    return _to_detail_response(db, risk)


@router.delete(
    "/{risk_id}/datasets/{dataset_id}",
    response_model=RiskDetailResponse
)
def unlink_dataset(
    risk_id: str,
    dataset_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin", "steward"))
):

    risk = _get_risk_or_404(risk_id, db, current_user)

    link = (
        db.query(RiskDatasetLink)
        .filter(RiskDatasetLink.risk_id == risk.id, RiskDatasetLink.dataset_id == dataset_id)
        .first()
    )

    if not link:
        raise HTTPException(status_code=404, detail="Link not found")

    db.delete(link)

    log_audit_event(
        db,
        organization_id=current_user.organization_id,
        action="risk.unlink_dataset",
        actor_user_id=current_user.id,
        actor_email=current_user.email,
        resource_type="risk",
        resource_id=risk.id,
        details=f"Unlinked risk '{risk.title}' from a dataset",
    )

    db.commit()

    return _to_detail_response(db, risk)


@router.post(
    "/{risk_id}/processes",
    response_model=RiskDetailResponse
)
def link_process(
    risk_id: str,
    payload: RiskProcessLinkCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin", "steward"))
):

    risk = _get_risk_or_404(risk_id, db, current_user)
    process = _get_process_or_404(str(payload.process_id), db, current_user)

    existing = (
        db.query(RiskProcessLink)
        .filter(RiskProcessLink.risk_id == risk.id, RiskProcessLink.process_id == process.id)
        .first()
    )

    if existing:
        raise HTTPException(status_code=400, detail="This process is already linked to that risk.")

    db.add(RiskProcessLink(risk_id=risk.id, process_id=process.id))

    log_audit_event(
        db,
        organization_id=current_user.organization_id,
        action="risk.link_process",
        actor_user_id=current_user.id,
        actor_email=current_user.email,
        resource_type="risk",
        resource_id=risk.id,
        details=f"Linked risk '{risk.title}' to process '{process.name}'",
    )

    db.commit()

    return _to_detail_response(db, risk)


@router.delete(
    "/{risk_id}/processes/{process_id}",
    response_model=RiskDetailResponse
)
def unlink_process(
    risk_id: str,
    process_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin", "steward"))
):

    risk = _get_risk_or_404(risk_id, db, current_user)

    link = (
        db.query(RiskProcessLink)
        .filter(RiskProcessLink.risk_id == risk.id, RiskProcessLink.process_id == process_id)
        .first()
    )

    if not link:
        raise HTTPException(status_code=404, detail="Link not found")

    db.delete(link)

    log_audit_event(
        db,
        organization_id=current_user.organization_id,
        action="risk.unlink_process",
        actor_user_id=current_user.id,
        actor_email=current_user.email,
        resource_type="risk",
        resource_id=risk.id,
        details=f"Unlinked risk '{risk.title}' from a process",
    )

    db.commit()

    return _to_detail_response(db, risk)


@router.post(
    "/{risk_id}/controls",
    response_model=RiskDetailResponse
)
def link_control(
    risk_id: str,
    payload: RiskControlLinkCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin", "steward"))
):

    risk = _get_risk_or_404(risk_id, db, current_user)
    control = _get_control_or_404(str(payload.control_id), db, current_user)

    existing = (
        db.query(RiskControlLink)
        .filter(RiskControlLink.risk_id == risk.id, RiskControlLink.control_id == control.id)
        .first()
    )

    if existing:
        raise HTTPException(status_code=400, detail="This control is already linked to that risk.")

    db.add(RiskControlLink(risk_id=risk.id, control_id=control.id))

    log_audit_event(
        db,
        organization_id=current_user.organization_id,
        action="risk.link_control",
        actor_user_id=current_user.id,
        actor_email=current_user.email,
        resource_type="risk",
        resource_id=risk.id,
        details=f"Linked risk '{risk.title}' to control '{control.name}'",
    )

    db.commit()

    return _to_detail_response(db, risk)


@router.delete(
    "/{risk_id}/controls/{control_id}",
    response_model=RiskDetailResponse
)
def unlink_control(
    risk_id: str,
    control_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin", "steward"))
):

    risk = _get_risk_or_404(risk_id, db, current_user)

    link = (
        db.query(RiskControlLink)
        .filter(RiskControlLink.risk_id == risk.id, RiskControlLink.control_id == control_id)
        .first()
    )

    if not link:
        raise HTTPException(status_code=404, detail="Link not found")

    db.delete(link)

    log_audit_event(
        db,
        organization_id=current_user.organization_id,
        action="risk.unlink_control",
        actor_user_id=current_user.id,
        actor_email=current_user.email,
        resource_type="risk",
        resource_id=risk.id,
        details=f"Unlinked risk '{risk.title}' from a control",
    )

    db.commit()

    return _to_detail_response(db, risk)


@router.get(
    "/dataset/{dataset_id}",
    response_model=list[RiskResponse]
)
def list_risks_for_dataset(
    dataset_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):

    _get_dataset_or_404(dataset_id, db, current_user)

    risks = (
        db.query(Risk)
        .join(RiskDatasetLink, RiskDatasetLink.risk_id == Risk.id)
        .filter(RiskDatasetLink.dataset_id == dataset_id)
        .all()
    )

    return [_to_response(db, risk) for risk in risks]
