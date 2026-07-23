from fastapi import APIRouter
from fastapi import Depends
from fastapi import HTTPException

from sqlalchemy.orm import Session

from app.db.session import get_db

from app.models.data_quality import DataQuality
from app.models.dataset import Dataset
from app.models.user import User

from app.schemas.data_quality import DataQualityResponse
from app.schemas.data_quality import EffectiveQualityResponse

from app.services.lineage_quality_service import compute_effective_quality

from app.auth.dependencies import get_current_user


router = APIRouter(
    prefix="/api/data-quality",
    tags=["data-quality"]
)


@router.get(
    "",
    response_model=list[DataQualityResponse]
)
@router.get(
    "/",
    response_model=list[DataQualityResponse]
)
def list_data_quality(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):

    return (
        db.query(DataQuality)
        .join(Dataset, DataQuality.dataset_id == Dataset.id)
        .filter(Dataset.organization_id == current_user.organization_id)
        .all()
    )


@router.get(
    "/dataset/{dataset_id}",
    response_model=DataQualityResponse
)
def get_data_quality_for_dataset(
    dataset_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):

    record = (
        db.query(DataQuality)
        .join(Dataset, DataQuality.dataset_id == Dataset.id)
        .filter(
            DataQuality.dataset_id == dataset_id,
            Dataset.organization_id == current_user.organization_id
        )
        .first()
    )

    if not record:

        raise HTTPException(
            status_code=404,
            detail="No data quality profile found for this dataset"
        )

    return record


@router.get(
    "/dataset/{dataset_id}/effective",
    response_model=EffectiveQualityResponse
)
def get_effective_quality_for_dataset(
    dataset_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Lineage-adjusted quality score.

    Blends a dataset's own profiled quality (if any) with what it inherits
    from upstream datasets, adjusted by how well each connecting lineage
    edge documents its transformation and filter logic. A well-documented
    edge can lift the downstream score above a flat inheritance; a poorly
    documented one pulls it down.
    """

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

    return compute_effective_quality(dataset_id, db)
