import csv
import io

from fastapi import APIRouter
from fastapi import Depends
from fastapi import File
from fastapi import HTTPException
from fastapi import UploadFile

from sqlalchemy.orm import Session

from app.db.session import get_db

from app.models.dataset import Dataset
from app.models.governance import BusinessGlossaryTerm
from app.models.user import User

from app.schemas.governance import BusinessGlossaryTermCreate
from app.schemas.governance import BusinessGlossaryTermResponse
from app.schemas.governance import BusinessGlossaryTermUpdate
from app.schemas.governance import DatasetCertificationUpdate
from app.schemas.governance import DatasetGovernanceUpdate
from app.schemas.governance import DatasetTagUpdate
from app.schemas.governance import GlossaryBulkImportResponse
from app.schemas.governance import GovernanceScorecard

from app.auth.dependencies import get_current_user
from app.auth.dependencies import require_role
from app.services.audit_service import log_audit_event


router = APIRouter(
    prefix="/api/governance",
    tags=["governance"]
)

# Sanity ceilings, not a product limit - a spreadsheet of term
# definitions is small text, so these are generous enough that no
# realistic bulk import ever hits them, while still failing fast with
# a clear message instead of trying to process something enormous.
MAX_GLOSSARY_IMPORT_BYTES = 2 * 1024 * 1024
MAX_GLOSSARY_IMPORT_ROWS = 1000


def get_dataset_or_404(
    dataset_id: str,
    db: Session,
    current_user: User
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

        raise HTTPException(
            status_code=404,
            detail="Dataset not found"
        )

    return dataset


@router.get("/overview")
def governance_overview(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):

    datasets = (
        db.query(Dataset)
        .filter(Dataset.organization_id == current_user.organization_id)
        .all()
    )

    total_datasets = len(datasets)

    average_score = 0

    if datasets:

        average_score = int(
            sum(dataset.governance_score for dataset in datasets)
            / total_datasets
        )

    missing_stewards = len([
        dataset for dataset in datasets
        if not dataset.steward
    ])

    uncertified = len([
        dataset for dataset in datasets
        if dataset.certification != "VERIFIED"
    ])

    critical = len([
        dataset for dataset in datasets
        if dataset.governance_status == "CRITICAL"
    ])

    glossary_terms = (
        db.query(BusinessGlossaryTerm)
        .filter(BusinessGlossaryTerm.organization_id == current_user.organization_id)
        .count()
    )

    return {
        "total_datasets": total_datasets,
        "average_governance_score": average_score,
        "missing_stewards": missing_stewards,
        "uncertified_datasets": uncertified,
        "critical_datasets": critical,
        "glossary_terms": glossary_terms,
    }


@router.get(
    "/scorecards",
    response_model=list[GovernanceScorecard]
)
def list_governance_scorecards(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):

    return (
        db.query(Dataset)
        .filter(Dataset.organization_id == current_user.organization_id)
        .all()
    )


@router.get(
    "/datasets/{dataset_id}/scorecard",
    response_model=GovernanceScorecard
)
def get_governance_scorecard(
    dataset_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):

    return get_dataset_or_404(
        dataset_id,
        db,
        current_user
    )


@router.patch(
    "/datasets/{dataset_id}",
    response_model=GovernanceScorecard
)
def update_dataset_governance(
    dataset_id: str,
    payload: DatasetGovernanceUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin", "steward"))
):

    dataset = get_dataset_or_404(
        dataset_id,
        db,
        current_user
    )

    updates = payload.model_dump(
        exclude_unset=True
    )

    if updates.get("certification") == "VERIFIED" and dataset.certification != "VERIFIED":

        raise HTTPException(
            status_code=400,
            detail=(
                "Datasets can only be certified VERIFIED through a certification "
                "request (POST /api/certification-requests) - a different admin "
                "has to approve it, not the person setting the field."
            )
        )

    for field, value in updates.items():
        setattr(dataset, field, value)

    log_audit_event(
        db,
        organization_id=current_user.organization_id,
        action="governance.update",
        actor_user_id=current_user.id,
        actor_email=current_user.email,
        resource_type="dataset",
        resource_id=dataset.id,
        details=f"Updated fields: {', '.join(updates.keys())}",
    )

    db.commit()
    db.refresh(dataset)

    return dataset


@router.patch(
    "/datasets/{dataset_id}/certification",
    response_model=GovernanceScorecard
)
def certify_dataset(
    dataset_id: str,
    payload: DatasetCertificationUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin", "steward"))
):

    dataset = get_dataset_or_404(
        dataset_id,
        db,
        current_user
    )

    if payload.certification == "VERIFIED" and dataset.certification != "VERIFIED":

        raise HTTPException(
            status_code=400,
            detail=(
                "Datasets can only be certified VERIFIED through a certification "
                "request (POST /api/certification-requests) - a different admin "
                "has to approve it, not the person setting the field."
            )
        )

    dataset.certification = payload.certification

    log_audit_event(
        db,
        organization_id=current_user.organization_id,
        action="governance.certify",
        actor_user_id=current_user.id,
        actor_email=current_user.email,
        resource_type="dataset",
        resource_id=dataset.id,
        details=f"Certification set to {payload.certification}",
    )

    db.commit()
    db.refresh(dataset)

    return dataset


@router.patch(
    "/datasets/{dataset_id}/tags",
    response_model=GovernanceScorecard
)
def update_dataset_tags(
    dataset_id: str,
    payload: DatasetTagUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin", "steward"))
):

    dataset = get_dataset_or_404(
        dataset_id,
        db,
        current_user
    )

    dataset.tags = payload.tags

    log_audit_event(
        db,
        organization_id=current_user.organization_id,
        action="governance.tag",
        actor_user_id=current_user.id,
        actor_email=current_user.email,
        resource_type="dataset",
        resource_id=dataset.id,
        details=f"Tags set to '{payload.tags}'",
    )

    db.commit()
    db.refresh(dataset)

    return dataset


@router.get(
    "/glossary",
    response_model=list[BusinessGlossaryTermResponse]
)
def list_glossary_terms(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):

    return (
        db.query(BusinessGlossaryTerm)
        .filter(BusinessGlossaryTerm.organization_id == current_user.organization_id)
        .order_by(BusinessGlossaryTerm.term.asc())
        .all()
    )


@router.post(
    "/glossary",
    response_model=BusinessGlossaryTermResponse
)
def create_glossary_term(
    payload: BusinessGlossaryTermCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin", "steward"))
):

    existing_term = (
        db.query(BusinessGlossaryTerm)
        .filter(
            BusinessGlossaryTerm.organization_id == current_user.organization_id,
            BusinessGlossaryTerm.term == payload.term
        )
        .first()
    )

    if existing_term:

        raise HTTPException(
            status_code=400,
            detail="Glossary term already exists"
        )

    term = BusinessGlossaryTerm(
        term=payload.term,
        definition=payload.definition,
        domain=payload.domain,
        owner=payload.owner,
        status=payload.status or "DRAFT",
        organization_id=current_user.organization_id
    )

    db.add(term)
    db.flush()

    log_audit_event(
        db,
        organization_id=current_user.organization_id,
        action="glossary.create",
        actor_user_id=current_user.id,
        actor_email=current_user.email,
        resource_type="glossary_term",
        resource_id=term.id,
        details=f"Created glossary term '{term.term}'",
    )

    db.commit()
    db.refresh(term)

    return term


@router.post(
    "/glossary/bulk-import",
    response_model=GlossaryBulkImportResponse,
)
def bulk_import_glossary_terms(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin", "steward"))
):
    """
    Bulk-creates glossary terms from a CSV - the highest-value slice of
    a broader "bulk upload everything" ask: a compliance/governance
    team routinely hands over a spreadsheet of 100+ term definitions,
    and POST /glossary one at a time doesn't scale to that the way it
    does for a single ad-hoc term.

    Expected columns: term, definition (both required), domain, owner,
    status (all optional) - matched case-insensitively with whitespace
    stripped, since a hand-edited spreadsheet header rarely comes back
    byte-identical to what's documented.

    Never fails the whole import for one bad row - a row missing a
    required field, or naming a term that's a duplicate (of an
    existing term in this org, or of an earlier row in the same file),
    is skipped and reported back in `skipped`, while every valid row
    still gets created. Partial success with a clear report is the
    right behavior for a bulk tool; all-or-nothing would mean one typo
    in row 80 throws away 79 good rows.
    """

    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Only .csv files are supported.")

    contents = file.file.read()

    if len(contents) > MAX_GLOSSARY_IMPORT_BYTES:
        raise HTTPException(
            status_code=400,
            detail="File is too large - please split it into smaller batches.",
        )

    try:
        # utf-8-sig transparently strips a BOM if Excel added one -
        # without this, the header's first column name (e.g. "term")
        # comes back as "﻿term" and silently fails the column-name
        # match below.
        text = contents.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise HTTPException(status_code=400, detail="Couldn't read this file as UTF-8 text.")

    reader = csv.DictReader(io.StringIO(text))

    if not reader.fieldnames:
        raise HTTPException(status_code=400, detail="This CSV has no header row.")

    normalized_fields = {
        (name or "").strip().lower(): name for name in reader.fieldnames
    }

    if "term" not in normalized_fields or "definition" not in normalized_fields:
        raise HTTPException(
            status_code=400,
            detail="CSV must have at least 'term' and 'definition' columns.",
        )

    rows = list(reader)

    if len(rows) > MAX_GLOSSARY_IMPORT_ROWS:
        raise HTTPException(
            status_code=400,
            detail=(
                f"This file has {len(rows)} rows - please split it into batches of "
                f"{MAX_GLOSSARY_IMPORT_ROWS} or fewer."
            ),
        )

    existing_terms = {
        existing.term.strip().lower()
        for existing in db.query(BusinessGlossaryTerm).filter(
            BusinessGlossaryTerm.organization_id == current_user.organization_id
        ).all()
    }

    domain_field = normalized_fields.get("domain")
    owner_field = normalized_fields.get("owner")
    status_field = normalized_fields.get("status")

    created_terms = []
    skipped_rows = []
    seen_in_file = set()

    # start=2: row 1 is the header, so the first data row is "row 2" -
    # matches what someone would count opening the file in a
    # spreadsheet, rather than a 0-indexed data-row number nobody
    # editing the CSV directly would think in.
    for index, row in enumerate(rows, start=2):
        term_text = (row.get(normalized_fields["term"]) or "").strip()
        definition_text = (row.get(normalized_fields["definition"]) or "").strip()

        if not term_text or not definition_text:
            skipped_rows.append({
                "row": index,
                "term": term_text or None,
                "reason": "Missing term or definition.",
            })
            continue

        key = term_text.lower()

        if key in existing_terms or key in seen_in_file:
            skipped_rows.append({
                "row": index,
                "term": term_text,
                "reason": "A term with this name already exists.",
            })
            continue

        term = BusinessGlossaryTerm(
            term=term_text,
            definition=definition_text,
            domain=((row.get(domain_field) or "").strip() or None) if domain_field else None,
            owner=((row.get(owner_field) or "").strip() or None) if owner_field else None,
            status=(((row.get(status_field) or "").strip().upper() or "DRAFT") if status_field else "DRAFT"),
            organization_id=current_user.organization_id,
        )

        db.add(term)
        seen_in_file.add(key)
        created_terms.append(term)

    db.flush()

    log_audit_event(
        db,
        organization_id=current_user.organization_id,
        action="glossary.bulk_import",
        actor_user_id=current_user.id,
        actor_email=current_user.email,
        resource_type="glossary_term",
        resource_id=None,
        details=(
            f"Bulk-imported {len(created_terms)} glossary term(s) from "
            f"'{file.filename}', skipped {len(skipped_rows)}"
        ),
    )

    db.commit()

    for term in created_terms:
        db.refresh(term)

    return GlossaryBulkImportResponse(
        created_count=len(created_terms),
        skipped_count=len(skipped_rows),
        created=created_terms,
        skipped=skipped_rows,
    )


@router.patch(
    "/glossary/{term_id}",
    response_model=BusinessGlossaryTermResponse
)
def update_glossary_term(
    term_id: str,
    payload: BusinessGlossaryTermUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin", "steward"))
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

        raise HTTPException(
            status_code=404,
            detail="Glossary term not found"
        )

    updates = payload.model_dump(
        exclude_unset=True
    )

    for field, value in updates.items():
        setattr(term, field, value)

    db.commit()
    db.refresh(term)

    return term
