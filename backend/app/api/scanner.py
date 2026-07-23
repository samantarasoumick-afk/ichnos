from fastapi import APIRouter
from fastapi import Depends
from fastapi import HTTPException

from sqlalchemy.orm import Session

from app.db.session import get_db

from app.models.user import User
from app.auth.dependencies import require_role

from app.services.lineage_discovery import LineageDiscoveryService
from app.services.dataset_ingestion_service import ingest_dataset_info

from app.models.source import DataSource

from app.connectors.registry import (
    get_scanner,
    supported_types,
    CONNECTION_ERRORS,
)

from app.services.audit_service import log_audit_event


router = APIRouter(
    prefix="/api/scanner",
    tags=["scanner"]
)


@router.post("/{source_id}")
def scan_source(
    source_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin", "steward"))
):

    # ----------------------------
    # Load Source (scoped to the caller's org so one tenant can't
    # trigger a scan of - or discover the existence of - another
    # tenant's source by guessing its id)
    # ----------------------------

    source = (
        db.query(DataSource)
        .filter(
            DataSource.id == source_id,
            DataSource.organization_id == current_user.organization_id
        )
        .first()
    )

    if source is None:
        raise HTTPException(
            status_code=404,
            detail="Source not found"
        )

    scanner_fn = get_scanner(source.type)

    if scanner_fn is None:

        raise HTTPException(
            status_code=400,
            detail=(
                f"Sources of type '{source.type}' are not yet supported. "
                f"Supported types: {', '.join(supported_types())}."
            )
        )

    # ----------------------------
    # Scan
    # ----------------------------

    try:

        scan_result = scanner_fn(
            source.connection_config
        )

        datasets = scan_result["datasets"]

        foreign_keys = scan_result["foreign_keys"]

    except CONNECTION_ERRORS as exc:

        raise HTTPException(
            status_code=502,
            detail=str(exc)
        )

    # ----------------------------
    # Process Every Dataset
    # ----------------------------

    for dataset_info in datasets:

        ingest_dataset_info(db, source, dataset_info, current_user)

    # ----------------------------
    # Discover Lineage
    # ----------------------------

    LineageDiscoveryService.discover(

        db=db,

        source_id=source.id,

        foreign_keys=foreign_keys,

        organization_id=source.organization_id,

    )

    log_audit_event(
        db,
        organization_id=current_user.organization_id,
        action="scanner.scan",
        actor_user_id=current_user.id,
        actor_email=current_user.email,
        resource_type="data_source",
        resource_id=source.id,
        details=f"Scanned '{source.name}': {len(datasets)} dataset(s), {len(foreign_keys)} foreign key(s)",
    )
    db.commit()

    # ----------------------------
    # Response
    # ----------------------------

    return {

        "message": "Scan completed successfully",

        "datasets_discovered": len(datasets),

        "foreign_keys_discovered": len(foreign_keys)

    }
