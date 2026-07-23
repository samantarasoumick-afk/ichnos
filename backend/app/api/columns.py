from uuid import UUID

from fastapi import APIRouter
from fastapi import Depends
from fastapi import HTTPException

from pydantic import BaseModel

from sqlalchemy.orm import Session

from app.db.session import get_db

from app.models.dataset import Dataset
from app.models.column import DatasetColumn
from app.models.user import User

from app.auth.dependencies import get_current_user
from app.auth.dependencies import require_role
from app.services.audit_service import log_audit_event


class ColumnDescriptionUpdate(BaseModel):
    description: str | None = None


router = APIRouter(
    prefix="/api/columns",
    tags=["columns"]
)


@router.get("")
@router.get("/")
def list_columns(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):

    return (
        db.query(DatasetColumn)
        .join(Dataset, DatasetColumn.dataset_id == Dataset.id)
        .filter(Dataset.organization_id == current_user.organization_id)
        .all()
    )


@router.get("/dataset/{dataset_id}")
def get_dataset_columns(
    dataset_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):

    try:

        dataset_uuid = UUID(dataset_id)

    except Exception:

        raise HTTPException(
            status_code=400,
            detail="Invalid dataset ID"
        )

    # Confirm the dataset belongs to the caller's org before
    # returning its columns.
    owned = (
        db.query(Dataset)
        .filter(
            Dataset.id == str(dataset_uuid),
            Dataset.organization_id == current_user.organization_id
        )
        .first()
    )

    if not owned:

        raise HTTPException(
            status_code=404,
            detail="Dataset not found"
        )

    return (
        db.query(DatasetColumn)
        .filter(
            DatasetColumn.dataset_id ==
            str(dataset_uuid)
        )
        .all()
    )


@router.patch("/{column_id}")
def update_column_description(
    column_id: str,
    payload: ColumnDescriptionUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin", "steward"))
):
    """
    Steward-authored business context for a single column - separate
    from classification (which has its own manual-override path) and
    never touched by a rescan.
    """

    column = (
        db.query(DatasetColumn)
        .join(Dataset, DatasetColumn.dataset_id == Dataset.id)
        .filter(
            DatasetColumn.id == column_id,
            Dataset.organization_id == current_user.organization_id,
        )
        .first()
    )

    if not column:

        raise HTTPException(
            status_code=404,
            detail="Column not found"
        )

    column.description = payload.description

    log_audit_event(
        db,
        organization_id=current_user.organization_id,
        action="column.update_description",
        actor_user_id=current_user.id,
        actor_email=current_user.email,
        resource_type="column",
        resource_id=column.id,
        details=f"Updated description for column '{column.name}'",
    )

    db.commit()
    db.refresh(column)

    return column
