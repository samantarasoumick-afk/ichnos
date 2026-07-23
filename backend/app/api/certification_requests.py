from typing import Optional

from fastapi import APIRouter
from fastapi import Depends
from fastapi import HTTPException

from sqlalchemy.orm import Session

from app.db.session import get_db

from app.models.certification_request import CertificationRequest
from app.models.dataset import Dataset
from app.models.user import User

from app.schemas.governance import CertificationRequestCreate
from app.schemas.governance import CertificationRequestResponse
from app.schemas.governance import CertificationRequestReview

from app.auth.dependencies import get_current_user
from app.auth.dependencies import require_role
from app.services.audit_service import log_audit_event

from datetime import datetime


router = APIRouter(
    prefix="/api/certification-requests",
    tags=["certification-requests"]
)


def _other_active_admins(db: Session, organization_id: str, excluding_user_id: str) -> int:
    """
    Same segregation-of-duties check users.py uses for "can't remove
    the last active admin" - reused here so a solo admin can still
    approve their own certification requests (the alternative is the
    workflow being permanently unusable for a one-person org), while
    an org with more than one admin gets real four-eyes review.
    """

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

        raise HTTPException(
            status_code=404,
            detail="Dataset not found"
        )

    return dataset


def _get_request_or_404(request_id: str, db: Session, current_user: User) -> CertificationRequest:

    request = (
        db.query(CertificationRequest)
        .join(Dataset, CertificationRequest.dataset_id == Dataset.id)
        .filter(
            CertificationRequest.id == request_id,
            Dataset.organization_id == current_user.organization_id
        )
        .first()
    )

    if not request:

        raise HTTPException(
            status_code=404,
            detail="Certification request not found"
        )

    return request


def _to_response(request: CertificationRequest) -> CertificationRequestResponse:

    return CertificationRequestResponse(
        id=request.id,
        dataset_id=request.dataset_id,
        requested_by=request.requested_by,
        requested_by_email=request.requester.email if request.requester else None,
        request_note=request.request_note,
        status=request.status,
        reviewed_by=request.reviewed_by,
        reviewed_by_email=request.reviewer.email if request.reviewer else None,
        review_note=request.review_note,
        created_at=request.created_at,
        reviewed_at=request.reviewed_at,
    )


@router.get(
    "",
    response_model=list[CertificationRequestResponse]
)
@router.get(
    "/",
    response_model=list[CertificationRequestResponse]
)
def list_certification_requests(
    status: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):

    query = (
        db.query(CertificationRequest)
        .join(Dataset, CertificationRequest.dataset_id == Dataset.id)
        .filter(Dataset.organization_id == current_user.organization_id)
    )

    if status:
        query = query.filter(CertificationRequest.status == status.upper())

    requests = query.order_by(CertificationRequest.created_at.desc()).all()

    return [_to_response(r) for r in requests]


@router.post(
    "",
    response_model=CertificationRequestResponse
)
@router.post(
    "/",
    response_model=CertificationRequestResponse
)
def create_certification_request(
    payload: CertificationRequestCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin", "steward"))
):

    dataset = _get_dataset_or_404(str(payload.dataset_id), db, current_user)

    existing_pending = (
        db.query(CertificationRequest)
        .filter(
            CertificationRequest.dataset_id == dataset.id,
            CertificationRequest.status == "PENDING"
        )
        .first()
    )

    if existing_pending:

        raise HTTPException(
            status_code=400,
            detail="This dataset already has a pending certification request."
        )

    request = CertificationRequest(
        dataset_id=dataset.id,
        requested_by=current_user.id,
        request_note=payload.request_note,
        status="PENDING",
    )

    db.add(request)

    # Visible in the catalog immediately - a request being open is
    # itself useful information, not just its eventual outcome.
    dataset.certification = "IN_REVIEW"

    db.flush()

    log_audit_event(
        db,
        organization_id=current_user.organization_id,
        action="certification_request.create",
        actor_user_id=current_user.id,
        actor_email=current_user.email,
        resource_type="dataset",
        resource_id=dataset.id,
        details=f"Requested certification for '{dataset.schema_name}.{dataset.name}'",
    )

    db.commit()
    db.refresh(request)

    return _to_response(request)


@router.post(
    "/{request_id}/approve",
    response_model=CertificationRequestResponse
)
def approve_certification_request(
    request_id: str,
    payload: CertificationRequestReview,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin", "data_owner"))
):

    request = _get_request_or_404(request_id, db, current_user)

    if request.status != "PENDING":

        raise HTTPException(
            status_code=400,
            detail="Only a pending certification request can be approved."
        )

    if request.requested_by == current_user.id:

        if _other_active_admins(db, current_user.organization_id, current_user.id) > 0:

            raise HTTPException(
                status_code=400,
                detail=(
                    "You can't approve your own certification request - "
                    "have another admin review it."
                )
            )

    dataset = request.dataset

    request.status = "APPROVED"
    request.reviewed_by = current_user.id
    request.review_note = payload.review_note
    request.reviewed_at = datetime.utcnow()

    dataset.certification = "VERIFIED"

    log_audit_event(
        db,
        organization_id=current_user.organization_id,
        action="certification_request.approve",
        actor_user_id=current_user.id,
        actor_email=current_user.email,
        resource_type="dataset",
        resource_id=dataset.id,
        details=f"Approved certification for '{dataset.schema_name}.{dataset.name}'",
    )

    db.commit()
    db.refresh(request)

    return _to_response(request)


@router.post(
    "/{request_id}/reject",
    response_model=CertificationRequestResponse
)
def reject_certification_request(
    request_id: str,
    payload: CertificationRequestReview,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin", "data_owner"))
):

    request = _get_request_or_404(request_id, db, current_user)

    if request.status != "PENDING":

        raise HTTPException(
            status_code=400,
            detail="Only a pending certification request can be rejected."
        )

    dataset = request.dataset

    request.status = "REJECTED"
    request.reviewed_by = current_user.id
    request.review_note = payload.review_note
    request.reviewed_at = datetime.utcnow()

    dataset.certification = "DRAFT"

    log_audit_event(
        db,
        organization_id=current_user.organization_id,
        action="certification_request.reject",
        actor_user_id=current_user.id,
        actor_email=current_user.email,
        resource_type="dataset",
        resource_id=dataset.id,
        details=f"Rejected certification for '{dataset.schema_name}.{dataset.name}'"
                + (f": {payload.review_note}" if payload.review_note else ""),
    )

    db.commit()
    db.refresh(request)

    return _to_response(request)
