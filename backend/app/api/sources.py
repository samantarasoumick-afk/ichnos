import json

from typing import Optional

from fastapi import APIRouter
from fastapi import Depends
from fastapi import File
from fastapi import Form
from fastapi import HTTPException
from fastapi import UploadFile

from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.source import DataSource
from app.models.user import User
from app.schemas.source import SourceCreate
from app.schemas.tableau import TableauConnectRequest
from app.auth.dependencies import get_current_user
from app.auth.dependencies import require_role
from app.services.audit_service import log_audit_event
from app.services.entitlements import enforce_source_limit
from app.services.dataset_ingestion_service import ingest_dataset_info
from app.services.dbt_ingestion_service import ingest_dbt_project
from app.services.tableau_ingestion_service import ingest_tableau_workbooks
from app.connectors.file_scanner import parse_csv_upload
from app.connectors.tableau_connector import (
    TableauConnectionError,
    fetch_workbooks_with_upstream_tables,
)


# Not a hard product limit, just a sanity ceiling so a huge accidental
# upload fails fast with a clear message instead of exhausting memory.
MAX_UPLOAD_BYTES = 10 * 1024 * 1024

# dbt artifacts (manifest.json/catalog.json) are structured metadata
# for an entire project, not one table's worth of data - a real
# project's manifest can run several MB, so this gets a higher cap
# than the CSV upload above.
MAX_DBT_UPLOAD_BYTES = 20 * 1024 * 1024


router = APIRouter(
    prefix="/api/sources",
    tags=["sources"]
)


@router.get("")
@router.get("/")
def list_sources(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):

    return (
        db.query(DataSource)
        .filter(DataSource.organization_id == current_user.organization_id)
        .all()
    )


@router.post("")
@router.post("/")
def create_source(
    source: SourceCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin", "steward"))
):

    enforce_source_limit(db, current_user)

    existing_source = (
        db.query(DataSource)
        .filter(
            DataSource.organization_id == current_user.organization_id,
            DataSource.name == source.name
        )
        .first()
    )

    if existing_source:

        raise HTTPException(
            status_code=400,
            detail="Source already exists"
        )

    new_source = DataSource(
        name=source.name,
        type=source.type,
        connection_config=source.connection_config,
        organization_id=current_user.organization_id
    )

    db.add(new_source)
    db.flush()

    log_audit_event(
        db,
        organization_id=current_user.organization_id,
        action="source.create",
        actor_user_id=current_user.id,
        actor_email=current_user.email,
        resource_type="data_source",
        resource_id=new_source.id,
        details=f"Created source '{new_source.name}' ({new_source.type})",
    )

    db.commit()

    db.refresh(new_source)

    return new_source


@router.post("/upload")
def upload_file_source(
    name: str = Form(...),
    table_name: str = Form(...),
    schema_name: str = Form("uploads"),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin", "steward"))
):
    """
    Onboards a dataset from an uploaded CSV instead of a live
    connection - for orgs that can't grant live database access yet
    (firewalled on-prem systems, a pilot not ready to hand over
    credentials, or data that only exists as an export). Runs the
    file through the exact same ingestion pipeline a live scan uses,
    so classification, data quality, and governance work identically
    either way.
    """

    if not file.filename or not file.filename.lower().endswith(".csv"):

        raise HTTPException(
            status_code=400,
            detail="Only .csv files are supported right now."
        )

    enforce_source_limit(db, current_user)

    existing_source = (
        db.query(DataSource)
        .filter(
            DataSource.organization_id == current_user.organization_id,
            DataSource.name == name
        )
        .first()
    )

    if existing_source:

        raise HTTPException(
            status_code=400,
            detail="Source already exists"
        )

    contents = file.file.read()

    if len(contents) > MAX_UPLOAD_BYTES:

        raise HTTPException(
            status_code=400,
            detail="File is too large - please keep uploads under 10MB."
        )

    try:

        scan_result = parse_csv_upload(
            contents,
            table_name=table_name,
            schema_name=schema_name or "uploads",
        )

    except ValueError as exc:

        raise HTTPException(
            status_code=400,
            detail=str(exc)
        )

    new_source = DataSource(
        name=name,
        type="file_upload",
        connection_config={
            "original_filename": file.filename,
            "uploaded_by": current_user.email,
        },
        organization_id=current_user.organization_id
    )

    db.add(new_source)
    db.flush()

    dataset = ingest_dataset_info(
        db,
        new_source,
        scan_result["datasets"][0],
        current_user,
    )

    log_audit_event(
        db,
        organization_id=current_user.organization_id,
        action="source.upload",
        actor_user_id=current_user.id,
        actor_email=current_user.email,
        resource_type="data_source",
        resource_id=new_source.id,
        details=f"Uploaded '{file.filename}' as dataset '{schema_name}.{table_name}'",
    )

    db.commit()

    return {
        "message": "File uploaded and processed successfully",
        "source_id": new_source.id,
        "dataset_id": dataset.id,
    }


@router.post("/upload/dbt")
def upload_dbt_source(
    name: str = Form(...),
    manifest_file: UploadFile = File(...),
    catalog_file: Optional[UploadFile] = File(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin", "steward"))
):
    """
    Onboards an entire dbt project from its compiled artifacts rather
    than a live connection - dbt has no "scan me" API, but its
    manifest.json already has every model's schema/columns and the
    exact model-to-model dependency graph, which becomes real lineage
    (see dbt_ingestion_service.py) instead of something a steward has
    to document by hand. catalog.json (produced by `dbt docs
    generate`) is optional but recommended - without it, models still
    get ingested, just with "unknown" column types instead of the
    real warehouse-introspected ones.
    """

    if not manifest_file.filename or not manifest_file.filename.lower().endswith(".json"):

        raise HTTPException(
            status_code=400,
            detail="manifest_file must be a .json file (dbt's target/manifest.json)."
        )

    enforce_source_limit(db, current_user)

    existing_source = (
        db.query(DataSource)
        .filter(
            DataSource.organization_id == current_user.organization_id,
            DataSource.name == name
        )
        .first()
    )

    if existing_source:

        raise HTTPException(
            status_code=400,
            detail="Source already exists"
        )

    manifest_bytes = manifest_file.file.read()

    if len(manifest_bytes) > MAX_DBT_UPLOAD_BYTES:

        raise HTTPException(
            status_code=400,
            detail="manifest.json is too large - please keep uploads under 20MB."
        )

    try:
        manifest = json.loads(manifest_bytes)
    except json.JSONDecodeError:
        raise HTTPException(
            status_code=400,
            detail="manifest.json is not valid JSON."
        )

    if not isinstance(manifest, dict) or "nodes" not in manifest:

        raise HTTPException(
            status_code=400,
            detail="This doesn't look like a dbt manifest.json (missing 'nodes')."
        )

    catalog = {}

    if catalog_file is not None and catalog_file.filename:

        if not catalog_file.filename.lower().endswith(".json"):

            raise HTTPException(
                status_code=400,
                detail="catalog_file must be a .json file (dbt's target/catalog.json)."
            )

        catalog_bytes = catalog_file.file.read()

        if len(catalog_bytes) > MAX_DBT_UPLOAD_BYTES:

            raise HTTPException(
                status_code=400,
                detail="catalog.json is too large - please keep uploads under 20MB."
            )

        try:
            catalog = json.loads(catalog_bytes)
        except json.JSONDecodeError:
            raise HTTPException(
                status_code=400,
                detail="catalog.json is not valid JSON."
            )

    new_source = DataSource(
        name=name,
        type="dbt",
        connection_config={
            "manifest_filename": manifest_file.filename,
            "catalog_filename": catalog_file.filename if catalog_file else None,
            "uploaded_by": current_user.email,
        },
        organization_id=current_user.organization_id
    )

    db.add(new_source)
    db.flush()

    summary = ingest_dbt_project(db, new_source, manifest, catalog, current_user)

    log_audit_event(
        db,
        organization_id=current_user.organization_id,
        action="source.upload_dbt",
        actor_user_id=current_user.id,
        actor_email=current_user.email,
        resource_type="data_source",
        resource_id=new_source.id,
        details=(
            f"Uploaded dbt project '{manifest_file.filename}': "
            f"{summary['datasets_discovered']} dataset(s), "
            f"{summary['lineage_edges_created']} lineage edge(s)"
        ),
    )

    db.commit()

    return {
        "message": "dbt project processed successfully",
        "source_id": new_source.id,
        "datasets_discovered": summary["datasets_discovered"],
        "lineage_edges_created": summary["lineage_edges_created"],
    }


@router.post("/connect/tableau")
def connect_tableau_source(
    payload: TableauConnectRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin", "steward"))
):
    """
    Onboards a Tableau site by its workbooks' lineage rather than a
    table inventory - Tableau has no schema to scan, so this doesn't
    go through the generic SCANNERS dispatch. Signs in with a
    Personal Access Token, queries the Metadata API (GraphQL) for
    every workbook's upstream tables, creates one pseudo-Dataset per
    workbook, and links each one to any already-cataloged Dataset
    (from a live scan or upload of another source) it reads from -
    "would this table's data show up in this workbook" is exactly the
    downstream-impact question lineage answers.
    """

    enforce_source_limit(db, current_user)

    existing_source = (
        db.query(DataSource)
        .filter(
            DataSource.organization_id == current_user.organization_id,
            DataSource.name == payload.name
        )
        .first()
    )

    if existing_source:

        raise HTTPException(
            status_code=400,
            detail="Source already exists"
        )

    try:

        workbooks = fetch_workbooks_with_upstream_tables(
            server_url=payload.server_url,
            site_content_url=payload.site_content_url,
            token_name=payload.token_name,
            token_value=payload.token_value,
        )

    except TableauConnectionError as exc:

        raise HTTPException(
            status_code=400,
            detail=str(exc)
        )

    new_source = DataSource(
        name=payload.name,
        type="tableau",
        connection_config={
            "server_url": payload.server_url,
            "site_content_url": payload.site_content_url,
            "token_name": payload.token_name,
            "token_value": payload.token_value,
        },
        organization_id=current_user.organization_id
    )

    db.add(new_source)
    db.flush()

    summary = ingest_tableau_workbooks(db, new_source, workbooks, current_user)

    log_audit_event(
        db,
        organization_id=current_user.organization_id,
        action="source.connect_tableau",
        actor_user_id=current_user.id,
        actor_email=current_user.email,
        resource_type="data_source",
        resource_id=new_source.id,
        details=(
            f"Connected Tableau site '{payload.site_content_url or 'Default'}': "
            f"{summary['workbooks_discovered']} workbook(s), "
            f"{summary['lineage_edges_created']} lineage edge(s)"
        ),
    )

    db.commit()

    return {
        "message": "Tableau site connected successfully",
        "source_id": new_source.id,
        "workbooks_discovered": summary["workbooks_discovered"],
        "lineage_edges_created": summary["lineage_edges_created"],
    }
