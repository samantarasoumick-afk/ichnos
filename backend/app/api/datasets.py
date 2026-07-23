from fastapi import APIRouter
from fastapi import Depends
from fastapi import HTTPException

from sqlalchemy.orm import Session

from app.db.session import get_db

from app.models.dataset import Dataset
from app.models.user import User

from app.schemas.dataset import DatasetResponse

from app.auth.dependencies import get_current_user

from app.services.ai_metadata_service import (
    generate_dataset_summary
)
from app.services.dataset_view_service import record_view

router = APIRouter(
    prefix="/api/datasets",
    tags=["datasets"]
)


@router.get(
    "",
    response_model=list[DatasetResponse]
)
@router.get(
    "/",
    response_model=list[DatasetResponse]
)
def list_datasets(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):

    datasets = (
        db.query(Dataset)
        .filter(Dataset.organization_id == current_user.organization_id)
        .all()
    )

    return datasets


def _get_org_dataset_or_404(dataset_id: str, db: Session, current_user: User) -> Dataset:

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


@router.get(
    "/{dataset_id}",
    response_model=DatasetResponse
)
def get_dataset(
    dataset_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):

    dataset = _get_org_dataset_or_404(dataset_id, db, current_user)

    # Only opening the detail page counts as a "view" - the catalog
    # list endpoint intentionally doesn't record one for every
    # dataset it happens to render a card for.
    record_view(db, dataset, current_user.id)

    return dataset


@router.get("/{dataset_id}/summary")
def dataset_summary(
    dataset_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):

    dataset = _get_org_dataset_or_404(dataset_id, db, current_user)

    return {
        "summary": generate_dataset_summary(
            dataset
        )
    }
