from fastapi import APIRouter
from fastapi import Depends
from fastapi import HTTPException

from sqlalchemy.orm import Session

from app.db.session import get_db

from app.models.column import DatasetColumn
from app.models.dataset import Dataset
from app.models.governance import BusinessGlossaryTerm
from app.models.glossary_link import GlossaryTermLink
from app.models.user import User

from app.schemas.glossary_link import GlossaryTermLinkCreate
from app.schemas.glossary_link import GlossaryTermLinkResponse

from app.auth.dependencies import get_current_user
from app.auth.dependencies import require_role
from app.services.audit_service import log_audit_event


router = APIRouter(
    prefix="/api/glossary-links",
    tags=["glossary-links"]
)


def _to_response(link: GlossaryTermLink, term: BusinessGlossaryTerm, column_name: str | None) -> GlossaryTermLinkResponse:

    return GlossaryTermLinkResponse(
        id=link.id,
        term_id=link.term_id,
        term=term.term,
        definition=term.definition,
        dataset_id=link.dataset_id,
        column_id=link.column_id,
        column_name=column_name,
        created_at=link.created_at,
    )


def _query_with_term_and_column(db: Session):

    return (
        db.query(GlossaryTermLink, BusinessGlossaryTerm, DatasetColumn)
        .join(BusinessGlossaryTerm, GlossaryTermLink.term_id == BusinessGlossaryTerm.id)
        .outerjoin(DatasetColumn, GlossaryTermLink.column_id == DatasetColumn.id)
    )


@router.post(
    "",
    response_model=GlossaryTermLinkResponse
)
@router.post(
    "/",
    response_model=GlossaryTermLinkResponse
)
def create_glossary_link(
    payload: GlossaryTermLinkCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin", "steward"))
):
    """
    The one thing that was missing entirely: an explicit link between
    a glossary term and something in the technical catalog. column_id
    null means the term describes the whole dataset; a real column_id
    means it defines that one column precisely.
    """

    term = (
        db.query(BusinessGlossaryTerm)
        .filter(
            BusinessGlossaryTerm.id == str(payload.term_id),
            BusinessGlossaryTerm.organization_id == current_user.organization_id
        )
        .first()
    )

    if not term:
        raise HTTPException(status_code=404, detail="Glossary term not found")

    dataset = (
        db.query(Dataset)
        .filter(
            Dataset.id == str(payload.dataset_id),
            Dataset.organization_id == current_user.organization_id
        )
        .first()
    )

    if not dataset:
        raise HTTPException(status_code=404, detail="Dataset not found")

    column_name = None

    if payload.column_id is not None:

        column = (
            db.query(DatasetColumn)
            .filter(
                DatasetColumn.id == str(payload.column_id),
                DatasetColumn.dataset_id == dataset.id
            )
            .first()
        )

        if not column:
            raise HTTPException(
                status_code=404,
                detail="Column not found on this dataset"
            )

        column_name = column.name

    # The DB unique constraint doesn't catch two dataset-level links
    # (column_id NULL on both sides) between the same term and
    # dataset, since SQL treats NULL as distinct from NULL in a
    # uniqueness check - so this is checked explicitly instead.
    existing = (
        db.query(GlossaryTermLink)
        .filter(
            GlossaryTermLink.term_id == term.id,
            GlossaryTermLink.dataset_id == dataset.id,
            GlossaryTermLink.column_id == (str(payload.column_id) if payload.column_id else None),
        )
        .first()
    )

    if existing:
        raise HTTPException(
            status_code=400,
            detail="This term is already linked to that dataset/column."
        )

    link = GlossaryTermLink(
        term_id=term.id,
        dataset_id=dataset.id,
        column_id=str(payload.column_id) if payload.column_id else None,
    )

    db.add(link)
    db.flush()

    log_audit_event(
        db,
        organization_id=current_user.organization_id,
        action="glossary.link",
        actor_user_id=current_user.id,
        actor_email=current_user.email,
        resource_type="dataset",
        resource_id=dataset.id,
        details=(
            f"Linked glossary term '{term.term}' to "
            f"{dataset.schema_name}.{dataset.name}"
            + (f".{column_name}" if column_name else "")
        ),
    )

    db.commit()

    return _to_response(link, term, column_name)


@router.delete("/{link_id}")
def delete_glossary_link(
    link_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin", "steward"))
):

    link = (
        db.query(GlossaryTermLink)
        .join(Dataset, GlossaryTermLink.dataset_id == Dataset.id)
        .filter(
            GlossaryTermLink.id == link_id,
            Dataset.organization_id == current_user.organization_id
        )
        .first()
    )

    if not link:
        raise HTTPException(status_code=404, detail="Link not found")

    db.delete(link)

    log_audit_event(
        db,
        organization_id=current_user.organization_id,
        action="glossary.unlink",
        actor_user_id=current_user.id,
        actor_email=current_user.email,
        resource_type="dataset",
        resource_id=link.dataset_id,
        details="Removed a glossary term link",
    )

    db.commit()

    return {"message": "Link removed"}


@router.get(
    "/dataset/{dataset_id}",
    response_model=list[GlossaryTermLinkResponse]
)
def list_links_for_dataset(
    dataset_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
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
        raise HTTPException(status_code=404, detail="Dataset not found")

    rows = (
        _query_with_term_and_column(db)
        .filter(GlossaryTermLink.dataset_id == dataset_id)
        .all()
    )

    return [
        _to_response(link, term, column.name if column else None)
        for link, term, column in rows
    ]


@router.get(
    "/term/{term_id}",
    response_model=list[GlossaryTermLinkResponse]
)
def list_links_for_term(
    term_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
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
        raise HTTPException(status_code=404, detail="Glossary term not found")

    rows = (
        _query_with_term_and_column(db)
        .filter(GlossaryTermLink.term_id == term_id)
        .all()
    )

    return [
        _to_response(link, term_row, column.name if column else None)
        for link, term_row, column in rows
    ]
