"""
Evaluates a dataset's ACTIVE data contract (if it has one) against
what discovery actually found - Phase 1 only checks schema shape
(missing required columns, type mismatches, unexpected nullability);
DQ threshold enforcement is a later phase, once quality_thresholds is
actually acted on rather than just stored.

Deliberately self-contained: it reads straight from dataset.columns
(already persisted by sync_columns() by the time this runs), not from
a scanner's raw dataset_info - so it can be called from anywhere a
Dataset's contract needs (re)checking, not just mid-scan.
"""

from datetime import datetime

from sqlalchemy.orm import Session

from app.models.dataset import Dataset
from app.services.audit_service import log_audit_event


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
