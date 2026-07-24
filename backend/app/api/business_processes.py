from fastapi import APIRouter
from fastapi import Depends
from fastapi import HTTPException

from sqlalchemy.orm import Session

from app.db.session import get_db

from app.models.business_process import BusinessProcess
from app.models.business_process import BusinessProcessLink
from app.models.dataset import Dataset
from app.models.glossary_link import GlossaryTermLink
from app.models.governance import BusinessGlossaryTerm
from app.models.user import User

from app.schemas.business_process import BusinessProcessCreate
from app.schemas.business_process import BusinessProcessDatasetSummary
from app.schemas.business_process import BusinessProcessLinkCreate
from app.schemas.business_process import BusinessProcessLinkResponse
from app.schemas.business_process import BusinessProcessResponse
from app.schemas.business_process import BusinessProcessUpdate

from app.auth.dependencies import get_current_user
from app.auth.dependencies import require_role
from app.services.audit_service import log_audit_event


router = APIRouter(
    prefix="/api/business-processes",
    tags=["business-processes"]
)


def _dataset_count(db: Session, process_id: str) -> int:

    return (
        db.query(BusinessProcessLink)
        .filter(BusinessProcessLink.process_id == process_id)
        .count()
    )


def _to_response(db: Session, process: BusinessProcess) -> BusinessProcessResponse:

    return BusinessProcessResponse(
        id=process.id,
        name=process.name,
        description=process.description,
        narrative=process.narrative,
        owner=process.owner,
        dataset_count=_dataset_count(db, process.id),
        created_at=process.created_at,
        updated_at=process.updated_at,
    )


def _humanize_dataset_name(dataset: Dataset) -> str:
    """
    Turns a raw table name like 'customer_ltv' into a business-glossary-
    friendly 'Customer Ltv'. Imperfect on abbreviations, but good
    enough as an editable starting point - a steward can rename the
    generated term at any time, same as any other glossary term.
    """

    return (
        (dataset.name or "")
        .replace("_", " ")
        .replace("-", " ")
        .strip()
        .title()
        or dataset.name
    )


def _auto_link_glossary_term(
    db: Session,
    dataset: Dataset,
    process: BusinessProcess,
    current_user: User,
) -> tuple[bool, str]:
    """
    The "different data types becomes part of Business Glossary" half
    of process modeling: linking a dataset to a process ensures it has
    a glossary term, reusing an existing term of the same name if one
    already exists rather than creating a duplicate. New terms land as
    DRAFT so a steward reviews the auto-generated definition before
    it's treated as authoritative.
    """

    term_text = _humanize_dataset_name(dataset)

    term = (
        db.query(BusinessGlossaryTerm)
        .filter(
            BusinessGlossaryTerm.organization_id == current_user.organization_id,
            BusinessGlossaryTerm.term == term_text,
        )
        .first()
    )

    created_term = False

    if not term:

        category_label = (dataset.data_category or "").title() or "Uncategorized"

        definition = (
            f"Auto-generated when {dataset.schema_name}.{dataset.name} was "
            f"linked to the '{process.name}' business process. "
            f"{category_label} data - review and refine this definition."
        )

        term = BusinessGlossaryTerm(
            term=term_text,
            definition=definition,
            domain=dataset.data_category,
            organization_id=current_user.organization_id,
            status="DRAFT",
        )

        db.add(term)
        db.flush()
        created_term = True

    existing_link = (
        db.query(GlossaryTermLink)
        .filter(
            GlossaryTermLink.term_id == term.id,
            GlossaryTermLink.dataset_id == dataset.id,
            GlossaryTermLink.column_id.is_(None),
        )
        .first()
    )

    if not existing_link:

        db.add(GlossaryTermLink(term_id=term.id, dataset_id=dataset.id, column_id=None))
        db.flush()

        log_audit_event(
            db,
            organization_id=current_user.organization_id,
            action="glossary.auto_link",
            actor_user_id=current_user.id,
            actor_email=current_user.email,
            resource_type="dataset",
            resource_id=dataset.id,
            details=(
                f"Auto-linked glossary term '{term.term}' to "
                f"{dataset.schema_name}.{dataset.name} via process '{process.name}'"
                + (" (new term)" if created_term else " (existing term reused)")
            ),
        )

    return created_term, term.term


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


@router.get(
    "",
    response_model=list[BusinessProcessResponse]
)
@router.get(
    "/",
    response_model=list[BusinessProcessResponse]
)
def list_business_processes(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):

    processes = (
        db.query(BusinessProcess)
        .filter(BusinessProcess.organization_id == current_user.organization_id)
        .order_by(BusinessProcess.name)
        .all()
    )

    return [_to_response(db, process) for process in processes]


@router.post(
    "",
    response_model=BusinessProcessResponse
)
@router.post(
    "/",
    response_model=BusinessProcessResponse
)
def create_business_process(
    payload: BusinessProcessCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin", "steward"))
):

    existing = (
        db.query(BusinessProcess)
        .filter(
            BusinessProcess.organization_id == current_user.organization_id,
            BusinessProcess.name == payload.name
        )
        .first()
    )

    if existing:
        raise HTTPException(status_code=400, detail="A business process with this name already exists")

    process = BusinessProcess(
        name=payload.name,
        description=payload.description,
        narrative=payload.narrative,
        owner=payload.owner,
        organization_id=current_user.organization_id,
    )

    db.add(process)
    db.flush()

    log_audit_event(
        db,
        organization_id=current_user.organization_id,
        action="business_process.create",
        actor_user_id=current_user.id,
        actor_email=current_user.email,
        resource_type="business_process",
        resource_id=process.id,
        details=f"Created business process '{process.name}'",
    )

    db.commit()
    db.refresh(process)

    return _to_response(db, process)


@router.patch(
    "/{process_id}",
    response_model=BusinessProcessResponse
)
def update_business_process(
    process_id: str,
    payload: BusinessProcessUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin", "steward"))
):

    process = _get_process_or_404(process_id, db, current_user)

    updates = payload.model_dump(exclude_unset=True)

    for field, value in updates.items():
        setattr(process, field, value)

    db.commit()
    db.refresh(process)

    return _to_response(db, process)


@router.delete("/{process_id}")
def delete_business_process(
    process_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin", "steward"))
):

    process = _get_process_or_404(process_id, db, current_user)

    db.query(BusinessProcessLink).filter(
        BusinessProcessLink.process_id == process.id
    ).delete(synchronize_session=False)

    db.delete(process)

    log_audit_event(
        db,
        organization_id=current_user.organization_id,
        action="business_process.delete",
        actor_user_id=current_user.id,
        actor_email=current_user.email,
        resource_type="business_process",
        resource_id=process_id,
        details=f"Deleted business process '{process.name}'",
    )

    db.commit()

    return {"message": "Business process deleted"}


@router.post(
    "/{process_id}/datasets",
    response_model=BusinessProcessLinkResponse
)
def link_dataset_to_process(
    process_id: str,
    payload: BusinessProcessLinkCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin", "steward"))
):

    process = _get_process_or_404(process_id, db, current_user)
    dataset = _get_dataset_or_404(str(payload.dataset_id), db, current_user)

    existing = (
        db.query(BusinessProcessLink)
        .filter(
            BusinessProcessLink.process_id == process.id,
            BusinessProcessLink.dataset_id == dataset.id,
        )
        .first()
    )

    if existing:
        raise HTTPException(status_code=400, detail="This dataset is already linked to that process.")

    link = BusinessProcessLink(process_id=process.id, dataset_id=dataset.id)
    db.add(link)
    db.flush()

    log_audit_event(
        db,
        organization_id=current_user.organization_id,
        action="business_process.link",
        actor_user_id=current_user.id,
        actor_email=current_user.email,
        resource_type="dataset",
        resource_id=dataset.id,
        details=f"Linked '{dataset.schema_name}.{dataset.name}' to process '{process.name}'",
    )

    term_created, term_name = _auto_link_glossary_term(db, dataset, process, current_user)

    db.commit()

    return BusinessProcessLinkResponse(
        id=link.id,
        process_id=link.process_id,
        process_name=process.name,
        dataset_id=link.dataset_id,
        created_at=link.created_at,
        glossary_term_created=term_created,
        glossary_term_name=term_name,
    )


@router.delete("/{process_id}/datasets/{dataset_id}")
def unlink_dataset_from_process(
    process_id: str,
    dataset_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin", "steward"))
):

    process = _get_process_or_404(process_id, db, current_user)

    link = (
        db.query(BusinessProcessLink)
        .filter(
            BusinessProcessLink.process_id == process.id,
            BusinessProcessLink.dataset_id == dataset_id,
        )
        .first()
    )

    if not link:
        raise HTTPException(status_code=404, detail="Link not found")

    db.delete(link)

    log_audit_event(
        db,
        organization_id=current_user.organization_id,
        action="business_process.unlink",
        actor_user_id=current_user.id,
        actor_email=current_user.email,
        resource_type="dataset",
        resource_id=dataset_id,
        details=f"Unlinked dataset from process '{process.name}'",
    )

    db.commit()

    return {"message": "Link removed"}


@router.get(
    "/{process_id}/datasets",
    response_model=list[BusinessProcessDatasetSummary]
)
def list_datasets_for_process(
    process_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):

    _get_process_or_404(process_id, db, current_user)

    rows = (
        db.query(Dataset)
        .join(BusinessProcessLink, BusinessProcessLink.dataset_id == Dataset.id)
        .filter(BusinessProcessLink.process_id == process_id)
        .all()
    )

    return rows


@router.get(
    "/dataset/{dataset_id}",
    response_model=list[BusinessProcessResponse]
)
def list_processes_for_dataset(
    dataset_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):

    _get_dataset_or_404(dataset_id, db, current_user)

    processes = (
        db.query(BusinessProcess)
        .join(BusinessProcessLink, BusinessProcessLink.process_id == BusinessProcess.id)
        .filter(BusinessProcessLink.dataset_id == dataset_id)
        .all()
    )

    return [_to_response(db, process) for process in processes]
