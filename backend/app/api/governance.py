from fastapi import APIRouter
from fastapi import Depends
from fastapi import HTTPException

from sqlalchemy.orm import Session

from app.db.session import get_db

from app.models.dataset import Dataset
from app.models.governance import BusinessGlossaryTerm
from app.models.user import User

from app.schemas.governance import BusinessGlossaryTermCreate
from app.schemas.governance import BusinessGlossaryTermResponse
from app.schemas.governance import BusinessGlossaryTermUpdate
from app.schemas.governance import DatasetCertificationUpdate
from app.schemas.governance import DatasetGovernanceUpdate
from app.schemas.governance import DatasetTagUpdate
from app.schemas.governance import GovernanceScorecard

from app.auth.dependencies import get_current_user
from app.auth.dependencies import require_role
from app.services.audit_service import log_audit_event


router = APIRouter(
    prefix="/api/governance",
    tags=["governance"]
)


def get_dataset_or_404(
    dataset_id: str,
    db: Session,
    current_user: User
):

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


@router.get("/overview")
def governance_overview(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):

    datasets = (
        db.query(Dataset)
        .filter(Dataset.organization_id == current_user.organization_id)
        .all()
    )

    total_datasets = len(datasets)

    average_score = 0

    if datasets:

        average_score = int(
            sum(dataset.governance_score for dataset in datasets)
            / total_datasets
        )

    missing_stewards = len([
        dataset for dataset in datasets
        if not dataset.steward
    ])

    uncertified = len([
        dataset for dataset in datasets
        if dataset.certification != "VERIFIED"
    ])

    critical = len([
        dataset for dataset in datasets
        if dataset.governance_status == "CRITICAL"
    ])

    glossary_terms = (
        db.query(BusinessGlossaryTerm)
        .filter(BusinessGlossaryTerm.organization_id == current_user.organization_id)
        .count()
    )

    return {
        "total_datasets": total_datasets,
        "average_governance_score": average_score,
        "missing_stewards": missing_stewards,
        "uncertified_datasets": uncertified,
        "critical_datasets": critical,
        "glossary_terms": glossary_terms,
    }


@router.get(
    "/scorecards",
    response_model=list[GovernanceScorecard]
)
def list_governance_scorecards(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):

    return (
        db.query(Dataset)
        .filter(Dataset.organization_id == current_user.organization_id)
        .all()
    )


@router.get(
    "/datasets/{dataset_id}/scorecard",
    response_model=GovernanceScorecard
)
def get_governance_scorecard(
    dataset_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):

    return get_dataset_or_404(
        dataset_id,
        db,
        current_user
    )


@router.patch(
    "/datasets/{dataset_id}",
    response_model=GovernanceScorecard
)
def update_dataset_governance(
    dataset_id: str,
    payload: DatasetGovernanceUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin", "steward"))
):

    dataset = get_dataset_or_404(
        dataset_id,
        db,
        current_user
    )

    updates = payload.model_dump(
        exclude_unset=True
    )

    if updates.get("certification") == "VERIFIED" and dataset.certification != "VERIFIED":

        raise HTTPException(
            status_code=400,
            detail=(
                "Datasets can only be certified VERIFIED through a certification "
                "request (POST /api/certification-requests) - a different admin "
                "has to approve it, not the person setting the field."
            )
        )

    for field, value in updates.items():
        setattr(dataset, field, value)

    log_audit_event(
        db,
        organization_id=current_user.organization_id,
        action="governance.update",
        actor_user_id=current_user.id,
        actor_email=current_user.email,
        resource_type="dataset",
        resource_id=dataset.id,
        details=f"Updated fields: {', '.join(updates.keys())}",
    )

    db.commit()
    db.refresh(dataset)

    return dataset


@router.patch(
    "/datasets/{dataset_id}/certification",
    response_model=GovernanceScorecard
)
def certify_dataset(
    dataset_id: str,
    payload: DatasetCertificationUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin", "steward"))
):

    dataset = get_dataset_or_404(
        dataset_id,
        db,
        current_user
    )

    if payload.certification == "VERIFIED" and dataset.certification != "VERIFIED":

        raise HTTPException(
            status_code=400,
            detail=(
                "Datasets can only be certified VERIFIED through a certification "
                "request (POST /api/certification-requests) - a different admin "
                "has to approve it, not the person setting the field."
            )
        )

    dataset.certification = payload.certification

    log_audit_event(
        db,
        organization_id=current_user.organization_id,
        action="governance.certify",
        actor_user_id=current_user.id,
        actor_email=current_user.email,
        resource_type="dataset",
        resource_id=dataset.id,
        details=f"Certification set to {payload.certification}",
    )

    db.commit()
    db.refresh(dataset)

    return dataset


@router.patch(
    "/datasets/{dataset_id}/tags",
    response_model=GovernanceScorecard
)
def update_dataset_tags(
    dataset_id: str,
    payload: DatasetTagUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin", "steward"))
):

    dataset = get_dataset_or_404(
        dataset_id,
        db,
        current_user
    )

    dataset.tags = payload.tags

    log_audit_event(
        db,
        organization_id=current_user.organization_id,
        action="governance.tag",
        actor_user_id=current_user.id,
        actor_email=current_user.email,
        resource_type="dataset",
        resource_id=dataset.id,
        details=f"Tags set to '{payload.tags}'",
    )

    db.commit()
    db.refresh(dataset)

    return dataset


@router.get(
    "/glossary",
    response_model=list[BusinessGlossaryTermResponse]
)
def list_glossary_terms(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):

    return (
        db.query(BusinessGlossaryTerm)
        .filter(BusinessGlossaryTerm.organization_id == current_user.organization_id)
        .order_by(BusinessGlossaryTerm.term.asc())
        .all()
    )


@router.post(
    "/glossary",
    response_model=BusinessGlossaryTermResponse
)
def create_glossary_term(
    payload: BusinessGlossaryTermCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin", "steward"))
):

    existing_term = (
        db.query(BusinessGlossaryTerm)
        .filter(
            BusinessGlossaryTerm.organization_id == current_user.organization_id,
            BusinessGlossaryTerm.term == payload.term
        )
        .first()
    )

    if existing_term:

        raise HTTPException(
            status_code=400,
            detail="Glossary term already exists"
        )

    term = BusinessGlossaryTerm(
        term=payload.term,
        definition=payload.definition,
        domain=payload.domain,
        owner=payload.owner,
        status=payload.status or "DRAFT",
        organization_id=current_user.organization_id
    )

    db.add(term)
    db.flush()

    log_audit_event(
        db,
        organization_id=current_user.organization_id,
        action="glossary.create",
        actor_user_id=current_user.id,
        actor_email=current_user.email,
        resource_type="glossary_term",
        resource_id=term.id,
        details=f"Created glossary term '{term.term}'",
    )

    db.commit()
    db.refresh(term)

    return term


@router.patch(
    "/glossary/{term_id}",
    response_model=BusinessGlossaryTermResponse
)
def update_glossary_term(
    term_id: str,
    payload: BusinessGlossaryTermUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin", "steward"))
):

    term = (
        db.query(BusinessGlossaryTerm)
        .filter(
            BusinessGlossaryTerm.id == term_id,
            BusinessGlossaryTerm.organization_id == current_user.organization_id
        )
        .first()
    )

    if not term:

        raise HTTPException(
            status_code=404,
            detail="Glossary term not found"
        )

    updates = payload.model_dump(
        exclude_unset=True
    )

    for field, value in updates.items():
        setattr(term, field, value)

    db.commit()
    db.refresh(term)

    return term
