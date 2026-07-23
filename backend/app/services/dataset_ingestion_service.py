"""
Turns one scanner's dataset_info dict (the shared contract every
connector produces - see postgres_scanner.py for the canonical shape)
into a persisted Dataset + columns + data quality profile.

Extracted out of app/api/scanner.py so a live database scan and a
one-off file upload go through exactly the same classification and
quality-scoring pipeline - a dataset shouldn't get weaker governance
just because it arrived as a CSV instead of a live connection.
"""

import json
from datetime import datetime

from sqlalchemy.orm import Session

from app.models.dataset import Dataset
from app.models.column import DatasetColumn
from app.models.data_quality import DataQuality
from app.models.source import DataSource
from app.models.user import User

from app.services.ai_metadata_service import generate_dataset_summary
from app.services.data_quality_service import DataQualityService
from app.services.data_contract_service import evaluate_contract

from app.utils.ai_enrichment import generate_dataset_description
from app.utils.privacy_engine import analyze_column
from app.utils.data_classification import classify_data_category


def sync_columns(db: Session, dataset: Dataset, dataset_info: dict):
    """
    Diff the columns currently in the source against what's already
    stored, instead of deleting everything and starting over. A
    steward who has hand-corrected a column's classification
    (classification_source == "MANUAL") keeps that correction across
    rescans; only the objective schema facts (data_type, nullable)
    refresh automatically for those columns. Columns still
    auto-classified get re-run through the privacy engine every scan
    so newly-sampled data can improve the classification. Columns
    genuinely dropped from the source table are removed; new ones are
    added.
    """

    existing_by_name = {
        column.name: column
        for column in (
            db.query(DatasetColumn)
            .filter(DatasetColumn.dataset_id == dataset.id)
            .all()
        )
    }

    column_samples = dataset_info.get("column_samples") or {}
    seen_names = set()

    for column_info in dataset_info["columns"]:

        name, data_type, is_nullable = column_info[0], column_info[1], column_info[2]
        seen_names.add(name)

        nullable = (is_nullable == "YES")
        samples = column_samples.get(name, [])

        existing = existing_by_name.get(name)

        # Example values are purely descriptive ("what does this data
        # look like"), not a classification judgment - refresh them
        # even for MANUAL columns, and cap the stored list so a wide
        # sample doesn't bloat the row.
        sample_values_json = json.dumps(samples[:5]) if samples else None

        if existing is not None:

            # Objective schema facts always refresh - these aren't
            # steward judgment calls, they're what the DB reports.
            existing.data_type = data_type
            existing.nullable = nullable
            existing.sample_values = sample_values_json

            if existing.classification_source == "MANUAL":
                # Respect the steward's override; don't touch
                # classification/sensitivity/etc.
                continue

            analysis = analyze_column(name, samples)

            existing.classification = analysis["classification"]
            existing.sensitivity_score = str(analysis["sensitivity_score"])
            existing.confidence = analysis["confidence"]
            existing.detection_reason = analysis["detection_reason"]
            existing.recommendation = analysis["recommendation"]
            existing.dpdp_category = analysis["dpdp_category"]
            existing.consent_required = analysis["consent_required"]
            existing.classification_source = "AUTO"

        else:

            analysis = analyze_column(name, samples)

            db.add(
                DatasetColumn(
                    dataset_id=dataset.id,
                    name=name,
                    data_type=data_type,
                    nullable=nullable,
                    classification=analysis["classification"],
                    sensitivity_score=str(analysis["sensitivity_score"]),
                    confidence=analysis["confidence"],
                    detection_reason=analysis["detection_reason"],
                    recommendation=analysis["recommendation"],
                    dpdp_category=analysis["dpdp_category"],
                    consent_required=analysis["consent_required"],
                    classification_source="AUTO",
                    sample_values=sample_values_json,
                )
            )

    # True schema drift: a column that existed before but is no
    # longer in the source table.
    for name, column in existing_by_name.items():
        if name not in seen_names:
            db.delete(column)


def ingest_dataset_info(
    db: Session,
    source: DataSource,
    dataset_info: dict,
    current_user: User,
) -> Dataset:
    """
    Find-or-create the Dataset for one dataset_info entry, sync its
    columns, regenerate its AI summary, and (re)compute its data
    quality profile. Commits internally (matching the transaction
    boundaries the scan endpoint already used) so a failure partway
    through a multi-dataset scan doesn't roll back datasets already
    processed.
    """

    dataset = (
        db.query(Dataset)
        .filter(
            Dataset.source_id == source.id,
            Dataset.schema_name == dataset_info["schema_name"],
            Dataset.name == dataset_info["table_name"],
        )
        .first()
    )

    if dataset:

        dataset.last_scanned_at = datetime.utcnow()

    else:

        dataset = Dataset(
            source_id=source.id,
            organization_id=current_user.organization_id,
            name=dataset_info["table_name"],
            schema_name=dataset_info["schema_name"],
            owner="SYSTEM",
            steward="DATA_TEAM",
            domain="GENERAL",
            certification="DRAFT",
            tags="",
            description=generate_dataset_description(
                dataset_info["table_name"],
                dataset_info["schema_name"],
                dataset_info["columns"]
            ),
            # Auto-classified once at creation, same "set once, steward
            # can override later" precedent as owner/steward/domain.
            data_category=classify_data_category(
                dataset_info["schema_name"],
                dataset_info["table_name"],
                [column_info[0] for column_info in dataset_info["columns"]],
            ),
            last_scanned_at=datetime.utcnow()
        )

        db.add(dataset)
        db.commit()
        db.refresh(dataset)

    sync_columns(db, dataset, dataset_info)

    # Flush (not commit) so dataset.columns reflects the columns just
    # added/updated above - the session has autoflush=False, so
    # without this, generate_dataset_summary() below could see a
    # stale column list for a brand-new dataset.
    db.flush()

    dataset.ai_summary = generate_dataset_summary(dataset)

    quality = DataQualityService.profile(dataset_info)

    existing_quality = (
        db.query(DataQuality)
        .filter(DataQuality.dataset_id == dataset.id)
        .first()
    )

    if existing_quality:

        existing_quality.completeness = quality["completeness"]
        existing_quality.uniqueness = quality["uniqueness"]
        existing_quality.validity = quality["validity"]
        existing_quality.consistency = quality["consistency"]
        existing_quality.freshness = quality["freshness"]
        existing_quality.overall_score = quality["overall_score"]

    else:

        db.add(
            DataQuality(
                dataset_id=dataset.id,
                completeness=quality["completeness"],
                uniqueness=quality["uniqueness"],
                validity=quality["validity"],
                consistency=quality["consistency"],
                freshness=quality["freshness"],
                overall_score=quality["overall_score"]
            )
        )

    # No-op if this dataset has no ACTIVE contract - contracts are
    # opt-in, so most datasets won't. Runs on every scan and file
    # upload alike, since both funnel through this one function.
    evaluate_contract(
        db,
        dataset,
        actor_user_id=current_user.id,
        actor_email=current_user.email,
    )

    db.commit()

    return dataset
