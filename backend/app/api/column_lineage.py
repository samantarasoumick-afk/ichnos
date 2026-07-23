from fastapi import APIRouter
from fastapi import Depends
from fastapi import HTTPException

from sqlalchemy.orm import Session

from app.db.session import get_db

from app.models.column_lineage import ColumnLineage
from app.models.dataset import Dataset
from app.models.user import User

from app.schemas.column_lineage import ColumnLineageResponse

from app.auth.dependencies import get_current_user


router = APIRouter(
    prefix="/api/column-lineage",
    tags=["column-lineage"]
)


@router.get("/dataset/{dataset_id}")
def get_column_lineage_for_dataset(
    dataset_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    One-hop column-level lineage for a dataset - the finer-grained
    companion to /api/lineage/{id}/dependencies and /impact, which
    only speak at the table level. Returns the raw edges rather than
    walking the full multi-hop graph (like LineageService does for
    table-level lineage) since a dataset's own column list is already
    a natural place to stop; a consumer wanting the full chain can
    follow "upstream" from each edge's own dataset in turn, same as
    the table-level lineage tab already does hop by hop.
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

    upstream = (
        db.query(ColumnLineage)
        .filter(ColumnLineage.downstream_dataset_id == dataset_id)
        .all()
    )

    downstream = (
        db.query(ColumnLineage)
        .filter(ColumnLineage.upstream_dataset_id == dataset_id)
        .all()
    )

    return {
        "upstream": [ColumnLineageResponse.model_validate(edge) for edge in upstream],
        "downstream": [ColumnLineageResponse.model_validate(edge) for edge in downstream],
    }
