from typing import Optional

from fastapi import APIRouter
from fastapi import Depends
from fastapi import HTTPException

from sqlalchemy.orm import Session

from app.db.session import get_db

from app.models.data_contract import DataContract
from app.models.dataset import Dataset
from app.models.user import User

from app.schemas.data_contract import DataContractCreate
from app.schemas.data_contract import DataContractResponse
from app.schemas.data_contract import DataContractUpdate
from app.schemas.data_contract import UpstreamContractBreach

from app.auth.dependencies import get_current_user
from app.auth.dependencies import require_role
from app.services.audit_service import log_audit_event
from app.services.data_contract_service import evaluate_contract
from app.services.data_contract_service import get_upstream_contract_breaches


router = APIRouter(
    prefix="/api/data-contracts",
    tags=["data-contracts"]
)


def get_dataset_or_404(dataset_id: str, db: Session, current_user: User) -> Dataset:

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


def get_contract_or_404(contract_id: str, db: Session, current_user: User) -> DataContract:

    contract = (
        db.query(DataContract)
        .join(Dataset, DataContract.dataset_id == Dataset.id)
        .filter(
            DataContract.id == contract_id,
            Dataset.organization_id == current_user.organization_id
        )
        .first()
    )

    if not contract:

        raise HTTPException(
            status_code=404,
            detail="Contract not found"
        )

    return contract


@router.get(
    "",
    response_model=list[DataContractResponse]
)
@router.get(
    "/",
    response_model=list[DataContractResponse]
)
def list_data_contracts(
    dataset_id: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):

    query = (
        db.query(DataContract)
        .join(Dataset, DataContract.dataset_id == Dataset.id)
        .filter(Dataset.organization_id == current_user.organization_id)
    )

    if dataset_id:
        query = query.filter(DataContract.dataset_id == dataset_id)

    return query.order_by(DataContract.created_at.desc()).all()


@router.get(
    "/dataset/{dataset_id}",
    response_model=list[DataContractResponse]
)
def list_contracts_for_dataset(
    dataset_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):

    get_dataset_or_404(dataset_id, db, current_user)

    return (
        db.query(DataContract)
        .filter(DataContract.dataset_id == dataset_id)
        .order_by(DataContract.version.desc())
        .all()
    )


@router.get(
    "/dataset/{dataset_id}/upstream-breaches",
    response_model=list[UpstreamContractBreach]
)
def list_upstream_contract_breaches(
    dataset_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Any upstream (via lineage) dataset whose ACTIVE contract is
    currently BREACHED - lets a viewer of this dataset see "something
    feeding this is broken" even if this dataset has no contract of
    its own, or its own contract is fine.
    """

    dataset = get_dataset_or_404(dataset_id, db, current_user)

    return get_upstream_contract_breaches(db, dataset)


@router.post(
    "",
    response_model=DataContractResponse
)
@router.post(
    "/",
    response_model=DataContractResponse
)
def create_data_contract(
    payload: DataContractCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin", "steward"))
):

    dataset = get_dataset_or_404(str(payload.dataset_id), db, current_user)

    latest_version = (
        db.query(DataContract)
        .filter(DataContract.dataset_id == dataset.id)
        .order_by(DataContract.version.desc())
        .first()
    )

    next_version = (latest_version.version + 1) if latest_version else 1

    contract = DataContract(
        dataset_id=dataset.id,
        version=next_version,
        status="DRAFT",
        owner=payload.owner,
        schema_expectations=payload.schema_expectations.model_dump(),
        quality_thresholds=payload.quality_thresholds,
        freshness_sla_hours=payload.freshness_sla_hours,
    )

    db.add(contract)
    db.flush()

    log_audit_event(
        db,
        organization_id=current_user.organization_id,
        action="contract.create",
        actor_user_id=current_user.id,
        actor_email=current_user.email,
        resource_type="dataset",
        resource_id=dataset.id,
        details=f"Drafted contract v{contract.version} for '{dataset.schema_name}.{dataset.name}'",
    )

    db.commit()
    db.refresh(contract)

    return contract


@router.patch(
    "/{contract_id}",
    response_model=DataContractResponse
)
def update_data_contract(
    contract_id: str,
    payload: DataContractUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin", "steward"))
):

    contract = get_contract_or_404(contract_id, db, current_user)

    if contract.status != "DRAFT":

        raise HTTPException(
            status_code=400,
            detail="Only a DRAFT contract can be edited - activate a new version instead"
        )

    updates = payload.model_dump(exclude_unset=True)

    if "schema_expectations" in updates and updates["schema_expectations"] is not None:
        updates["schema_expectations"] = payload.schema_expectations.model_dump()

    for field, value in updates.items():
        setattr(contract, field, value)

    db.commit()
    db.refresh(contract)

    return contract


@router.post(
    "/{contract_id}/activate",
    response_model=DataContractResponse
)
def activate_data_contract(
    contract_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin", "steward", "data_owner"))
):

    contract = get_contract_or_404(contract_id, db, current_user)

    if contract.status != "DRAFT":

        raise HTTPException(
            status_code=400,
            detail="Only a DRAFT contract can be activated"
        )

    # Only one ACTIVE contract per dataset at a time - the one being
    # replaced moves to DEPRECATED rather than being deleted, so its
    # history (and its last evaluation result) is preserved.
    other_active = (
        db.query(DataContract)
        .filter(
            DataContract.dataset_id == contract.dataset_id,
            DataContract.status == "ACTIVE"
        )
        .all()
    )

    for other in other_active:
        other.status = "DEPRECATED"

    contract.status = "ACTIVE"
    db.flush()

    dataset = get_dataset_or_404(contract.dataset_id, db, current_user)

    # Evaluate immediately against the dataset's current state, so a
    # freshly-activated contract doesn't sit at PENDING_EVALUATION
    # until the next scan/upload happens to run.
    evaluate_contract(
        db,
        dataset,
        actor_user_id=current_user.id,
        actor_email=current_user.email,
    )

    log_audit_event(
        db,
        organization_id=current_user.organization_id,
        action="contract.activate",
        actor_user_id=current_user.id,
        actor_email=current_user.email,
        resource_type="dataset",
        resource_id=dataset.id,
        details=f"Activated contract v{contract.version} for '{dataset.schema_name}.{dataset.name}'",
    )

    db.commit()
    db.refresh(contract)

    return contract


@router.post(
    "/{contract_id}/deprecate",
    response_model=DataContractResponse
)
def deprecate_data_contract(
    contract_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin", "steward", "data_owner"))
):

    contract = get_contract_or_404(contract_id, db, current_user)

    if contract.status != "ACTIVE":

        raise HTTPException(
            status_code=400,
            detail="Only an ACTIVE contract can be deprecated"
        )

    contract.status = "DEPRECATED"

    log_audit_event(
        db,
        organization_id=current_user.organization_id,
        action="contract.deprecate",
        actor_user_id=current_user.id,
        actor_email=current_user.email,
        resource_type="dataset",
        resource_id=contract.dataset_id,
        details=f"Deprecated contract v{contract.version}",
    )

    db.commit()
    db.refresh(contract)

    return contract
