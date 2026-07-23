from fastapi import APIRouter
from fastapi import Depends
from fastapi import Response

from sqlalchemy.orm import Session

from app.db.session import get_db

from app.models.dataset import Dataset
from app.models.organization import Organization
from app.models.user import User

from app.auth.dependencies import get_current_user

from app.services.compliance_report_service import generate_compliance_report_pdf
from app.services.audit_service import log_audit_event


router = APIRouter(
    prefix="/api/reports",
    tags=["reports"]
)


@router.get("/compliance")
@router.get("/compliance/")
def download_compliance_report(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):

    organization = (
        db.query(Organization)
        .filter(Organization.id == current_user.organization_id)
        .first()
    )

    datasets = (
        db.query(Dataset)
        .filter(Dataset.organization_id == current_user.organization_id)
        .all()
    )

    pdf_bytes = generate_compliance_report_pdf(
        organization_name=organization.name if organization else "Unknown Organization",
        generated_by_email=current_user.email,
        datasets=datasets,
    )

    log_audit_event(
        db,
        organization_id=current_user.organization_id,
        action="report.export",
        actor_user_id=current_user.id,
        actor_email=current_user.email,
        resource_type="compliance_report",
        details=f"Exported compliance report covering {len(datasets)} dataset(s)",
    )
    db.commit()

    filename = f"{(organization.slug if organization else 'org')}-compliance-report.pdf"

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"'
        }
    )
