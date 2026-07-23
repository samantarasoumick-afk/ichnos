from uuid import UUID

from app.services.lineage_service import LineageService
from fastapi import APIRouter
from fastapi import Depends
from fastapi import HTTPException

from app.services.lineage_discovery import LineageDiscoveryService
from app.connectors.registry import get_scanner
from app.models.source import DataSource
from app.models.dataset import Dataset
from app.models.user import User
from sqlalchemy.orm import Session

from app.db.session import get_db

from app.models.lineage import DatasetLineage

from app.auth.dependencies import get_current_user
from app.auth.dependencies import require_role
from app.services.audit_service import log_audit_event


from app.schemas.lineage import (
    LineageCreate,
    LineageResponse,
    LineageUpdate,
)

router = APIRouter(
    prefix="/api/lineage",
    tags=["lineage"]
)


def _org_dataset_ids(db: Session, current_user: User):

    rows = (
        db.query(Dataset.id)
        .filter(Dataset.organization_id == current_user.organization_id)
        .all()
    )

    return {row[0] for row in rows}


@router.post(
    "",
    response_model=LineageResponse
)
@router.post(
    "/",
    response_model=LineageResponse
)
def create_lineage(
    payload: LineageCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin", "steward"))
):

    org_dataset_ids = _org_dataset_ids(db, current_user)

    if (
        str(payload.upstream_dataset_id) not in org_dataset_ids
        or str(payload.downstream_dataset_id) not in org_dataset_ids
    ):

        raise HTTPException(
            status_code=404,
            detail="Dataset not found"
        )

    lineage = DatasetLineage(
        upstream_dataset_id=str(payload.upstream_dataset_id),
        downstream_dataset_id=str(payload.downstream_dataset_id),
        transformation_type=payload.transformation_type,
        transformation_description=payload.transformation_description,
        filter_logic=payload.filter_logic,
        # Always MANUAL through this endpoint - LineageDiscoveryService
        # is the only path that creates AUTO edges, from real FK
        # metadata at scan time.
        documentation_source="MANUAL",
    )

    db.add(lineage)
    db.flush()

    log_audit_event(
        db,
        organization_id=current_user.organization_id,
        action="lineage.create",
        actor_user_id=current_user.id,
        actor_email=current_user.email,
        resource_type="dataset_lineage",
        resource_id=lineage.id,
        details=(
            f"Documented lineage: {payload.upstream_dataset_id} -> "
            f"{payload.downstream_dataset_id}"
            + (f" ({payload.transformation_type})" if payload.transformation_type else "")
        ),
    )

    db.commit()

    db.refresh(lineage)

    return lineage


def _get_org_lineage_edge_or_404(edge_id: str, db: Session, current_user: User) -> DatasetLineage:

    org_dataset_ids = _org_dataset_ids(db, current_user)

    edge = (
        db.query(DatasetLineage)
        .filter(
            DatasetLineage.id == edge_id,
            DatasetLineage.upstream_dataset_id.in_(org_dataset_ids)
            | DatasetLineage.downstream_dataset_id.in_(org_dataset_ids)
        )
        .first()
    )

    if not edge:

        raise HTTPException(
            status_code=404,
            detail="Lineage edge not found"
        )

    return edge


@router.patch(
    "/{edge_id}",
    response_model=LineageResponse
)
def update_lineage(
    edge_id: str,
    payload: LineageUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin", "steward"))
):

    edge = _get_org_lineage_edge_or_404(edge_id, db, current_user)

    updates = payload.model_dump(exclude_unset=True)

    for field, value in updates.items():
        setattr(edge, field, value)

    # Documenting/correcting an edge is itself a manual act, even if
    # the edge originated from auto-discovery - it now carries a
    # human's explanation, so it shouldn't read as purely mechanical
    # anymore.
    if updates:
        edge.documentation_source = "MANUAL"

    log_audit_event(
        db,
        organization_id=current_user.organization_id,
        action="lineage.update",
        actor_user_id=current_user.id,
        actor_email=current_user.email,
        resource_type="dataset_lineage",
        resource_id=edge.id,
        details=f"Updated fields: {', '.join(updates.keys())}",
    )

    db.commit()
    db.refresh(edge)

    return edge


@router.get(
    "",
    response_model=list[LineageResponse]
)
@router.get(
    "/",
    response_model=list[LineageResponse]
)
def list_lineage(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):

    org_dataset_ids = _org_dataset_ids(db, current_user)

    return (
        db.query(DatasetLineage)
        .filter(
            DatasetLineage.upstream_dataset_id.in_(org_dataset_ids)
            | DatasetLineage.downstream_dataset_id.in_(org_dataset_ids)
        )
        .all()
    )


@router.get("/{dataset_id}/impact")
def impact_analysis(
    dataset_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):

    org_dataset_ids = _org_dataset_ids(db, current_user)

    if str(dataset_id) not in org_dataset_ids:

        raise HTTPException(
            status_code=404,
            detail="Dataset not found"
        )

    lineage = (
        db.query(DatasetLineage)
        .filter(
            DatasetLineage.upstream_dataset_id.in_(org_dataset_ids)
            | DatasetLineage.downstream_dataset_id.in_(org_dataset_ids)
        )
        .all()
    )

    impacts = LineageService.downstream(
        dataset_id,
        lineage,
    )

    return impacts

@router.get("/{dataset_id}/dependencies")
def dependency_analysis(
    dataset_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):

    org_dataset_ids = _org_dataset_ids(db, current_user)

    if str(dataset_id) not in org_dataset_ids:

        raise HTTPException(
            status_code=404,
            detail="Dataset not found"
        )

    lineage = (
        db.query(DatasetLineage)
        .filter(
            DatasetLineage.upstream_dataset_id.in_(org_dataset_ids)
            | DatasetLineage.downstream_dataset_id.in_(org_dataset_ids)
        )
        .all()
    )

    deps = LineageService.upstream(
        dataset_id,
        lineage,
    )

    return deps


@router.post("/discover/{source_id}")
def discover_lineage(
    source_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin", "steward"))
):

    source = (
        db.query(DataSource)
        .filter(
            DataSource.id == source_id,
            DataSource.organization_id == current_user.organization_id
        )
        .first()
    )

    if not source:
        raise HTTPException(
            status_code=404,
            detail="Source not found"
        )

    scanner_fn = get_scanner(source.type)

    if scanner_fn is None:
        raise HTTPException(
            status_code=400,
            detail=f"Sources of type '{source.type}' do not support lineage discovery yet."
        )

    scan_result = scanner_fn(
        source.connection_config
    )

    created = LineageDiscoveryService.discover(
        db=db,
        source_id=source.id,
        foreign_keys=scan_result["foreign_keys"],
        organization_id=source.organization_id,
    )

    return {
        "relationships_created": created
    }
