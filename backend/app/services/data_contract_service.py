"""
Evaluates a dataset's ACTIVE data contract (if it has one) against
what discovery actually found: schema shape (missing required
columns, type mismatches, unexpected nullability) and, if the
contract sets a quality_thresholds.min_overall_score, the dataset's
most recently profiled DataQuality.overall_score. Both feed the same
violations list and the same last_status/last_breach_details/audit-log
write - one breach mechanism, not two, so "Data Contract" means an
enforced contract rather than schema-only observability with a
quality field that's stored but never acted on.

Deliberately self-contained: it reads straight from dataset.columns
(already persisted by sync_columns() by the time this runs) and
queries DataQuality by dataset_id itself, rather than requiring the
caller to pass in a freshly-computed score - so it can be called from
anywhere a Dataset's contract needs (re)checking, not just mid-scan.
"""

from datetime import datetime

from sqlalchemy.orm import Session

from app.models.dataset import Dataset
from app.models.data_quality import DataQuality
from app.models.lineage import DatasetLineage
from app.services.audit_service import log_audit_event
from app.services.lineage_service import LineageService


def evaluate_contract(
    db: Session,
    dataset: Dataset,
    actor_user_id: str | None = None,
    actor_email: str | None = None,
):
    """
    No-op (returns None) if the dataset has no ACTIVE contract - most
    datasets won't, since contracts are opt-in. Does not commit; the
    caller's existing transaction boundary covers this write too.
    """

    contract = dataset.active_contract

    if contract is None:
        return None

    expected_columns = (contract.schema_expectations or {}).get("columns", [])
    actual_by_name = {column.name: column for column in dataset.columns}

    violations = []

    for expected in expected_columns:

        name = expected.get("name")
        required = expected.get("required", True)
        expected_type = expected.get("data_type")
        expected_nullable = expected.get("nullable")

        actual = actual_by_name.get(name)

        if actual is None:
            if required:
                violations.append(f"Missing required column '{name}'")
            continue

        # Type strings vary by source dialect (Postgres's "character
        # varying" vs MySQL's "varchar" vs a CSV's inferred "varchar"),
        # so this is a strict case-insensitive match - most reliable
        # when the contract was authored against the same source type
        # it's being checked against. Cross-source type normalization
        # is a known gap, not attempted here.
        if (
            expected_type
            and actual.data_type
            and actual.data_type.strip().lower() != expected_type.strip().lower()
        ):
            violations.append(
                f"Column '{name}' has type '{actual.data_type}', contract expects '{expected_type}'"
            )

        if expected_nullable is False and actual.nullable:
            violations.append(
                f"Column '{name}' is nullable but the contract requires NOT NULL"
            )

    min_score = (contract.quality_thresholds or {}).get("min_overall_score")

    if min_score is not None:

        # Autoflushes any pending DataQuality write from the same
        # transaction (dataset_ingestion_service writes the DataQuality
        # row and calls evaluate_contract back-to-back, before either
        # is committed), so this sees the just-computed score, not a
        # stale one from before the current scan.
        quality = (
            db.query(DataQuality)
            .filter(DataQuality.dataset_id == dataset.id)
            .first()
        )

        if quality is None or quality.overall_score is None:
            violations.append(
                "Contract requires a minimum data quality score of "
                f"{min_score}, but no quality profile exists yet for this dataset"
            )
        elif quality.overall_score < min_score:
            violations.append(
                f"Data quality score {quality.overall_score:.1f} is below "
                f"the contract's required minimum of {min_score}"
            )

    contract.last_evaluated_at = datetime.utcnow()

    if violations:

        contract.last_status = "BREACHED"
        contract.last_breach_details = "; ".join(violations)

        log_audit_event(
            db,
            organization_id=dataset.organization_id,
            action="contract.breach",
            actor_user_id=actor_user_id,
            actor_email=actor_email,
            resource_type="dataset",
            resource_id=dataset.id,
            details=(
                f"Contract v{contract.version} breached for "
                f"'{dataset.schema_name}.{dataset.name}': {contract.last_breach_details}"
            ),
        )

    else:

        contract.last_status = "COMPLIANT"
        contract.last_breach_details = None

    return contract


def get_upstream_contract_breaches(db: Session, dataset: Dataset) -> list[dict]:
    """
    Datasets with an ACTIVE, BREACHED contract reachable upstream of
    `dataset` via lineage - so a downstream consumer can see "something
    feeding this dataset is broken" even when this dataset's own
    contract (if it has one at all) is fine. This is what makes a
    contract breach a lineage-aware signal rather than something only
    visible if you happen to be looking at the exact dataset it broke
    on.

    Computed live on every call rather than a persisted flag, so it
    can never drift out of sync with the contracts/lineage edges it's
    derived from - the tradeoff is a query on every read, which is
    cheap at this scale (in-memory DFS over a pre-fetched edge list,
    same approach as the existing impact-analysis endpoint).
    """

    org_dataset_ids = {
        row[0]
        for row in (
            db.query(Dataset.id)
            .filter(Dataset.organization_id == dataset.organization_id)
            .all()
        )
    }

    lineage = (
        db.query(DatasetLineage)
        .filter(
            DatasetLineage.upstream_dataset_id.in_(org_dataset_ids)
            | DatasetLineage.downstream_dataset_id.in_(org_dataset_ids)
        )
        .all()
    )

    upstream_edges = LineageService.upstream(dataset.id, lineage)
    upstream_ids = {str(edge.upstream_dataset_id) for edge in upstream_edges}

    if not upstream_ids:
        return []

    upstream_datasets = (
        db.query(Dataset)
        .filter(Dataset.id.in_(upstream_ids))
        .all()
    )

    breaches = []

    for upstream_dataset in upstream_datasets:

        contract = upstream_dataset.active_contract

        if contract is not None and contract.last_status == "BREACHED":

            breaches.append({
                "dataset_id": upstream_dataset.id,
                "dataset_name": upstream_dataset.name,
                "schema_name": upstream_dataset.schema_name,
                "contract_id": contract.id,
                "contract_version": contract.version,
                "breach_details": contract.last_breach_details,
            })

    return breaches
