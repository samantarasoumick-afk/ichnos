import csv
import io

from datetime import datetime

from fastapi import APIRouter
from fastapi import Depends
from fastapi import HTTPException
from fastapi.responses import StreamingResponse

from sqlalchemy.orm import Session

from app.db.session import get_db

from app.models.column import DatasetColumn
from app.models.dataset import Dataset
from app.models.source import DataSource
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


@router.get("/{dataset_id}/export")
def export_dataset(
    dataset_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Downloads this dataset's catalog metadata as a CSV - one row per
    column, with the dataset-level facts (schema/name/owner/scores/
    system role/source) repeated on every row rather than split into a
    separate header block, so the file opens as one clean table in
    Excel/Sheets instead of needing manual reshaping first. This is a
    metadata export, not a data export: DatFe catalogs and profiles a
    source's schema, it doesn't warehouse the underlying rows, so
    there's no raw data to include even if a step below profiled a
    sample of it.

    Previously there was no per-dataset export at all - the only
    "download" anywhere in the product was the org-wide compliance PDF
    (see reports.py), which doesn't help someone who just wants this
    one dataset's column inventory in a spreadsheet.
    """

    dataset = _get_org_dataset_or_404(dataset_id, db, current_user)

    source = (
        db.query(DataSource).filter(DataSource.id == dataset.source_id).first()
        if dataset.source_id else None
    )

    columns = (
        db.query(DatasetColumn)
        .filter(DatasetColumn.dataset_id == dataset.id)
        .order_by(DatasetColumn.name)
        .all()
    )

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow([
        "schema_name", "dataset_name", "source_name", "owner", "system_role",
        "sensitivity_score", "quality_score", "trust_score", "governance_score",
        "column_name", "data_type", "nullable", "classification", "dpdp_category",
        "consent_required", "masked", "column_description", "sample_values",
    ])

    dataset_fields = [
        dataset.schema_name,
        dataset.name,
        source.name if source else "",
        dataset.owner or "",
        dataset.system_role or "",
        dataset.sensitivity_score or "",
        dataset.quality_score if dataset.quality_score is not None else "",
        dataset.trust_score if dataset.trust_score is not None else "",
        dataset.governance_score if dataset.governance_score is not None else "",
    ]

    if not columns:
        # A dataset with no profiled columns yet still gets a row, so
        # the export always reflects at least the dataset-level facts
        # rather than silently coming back as a header with no data.
        writer.writerow(dataset_fields + ["", "", "", "", "", "", "", "", ""])
    else:
        for column in columns:
            writer.writerow(dataset_fields + [
                column.name or "",
                column.data_type or "",
                column.nullable if column.nullable is not None else "",
                column.classification or "",
                column.dpdp_category or "",
                column.consent_required if column.consent_required is not None else "",
                column.masked if column.masked is not None else "",
                column.description or "",
                column.sample_values or "",
            ])

    buffer.seek(0)

    filename = f"{dataset.schema_name}.{dataset.name}-{datetime.utcnow().strftime('%Y%m%d-%H%M%S')}.csv"

    return StreamingResponse(
        iter([buffer.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


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
