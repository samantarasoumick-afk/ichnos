from typing import Optional

from fastapi import APIRouter
from fastapi import Depends
from fastapi import HTTPException

from pydantic import BaseModel

from sqlalchemy.orm import Session

from app.db.session import get_db

from app.models.user import User

from app.auth.dependencies import require_platform_admin
from app.services import platform_service
from app.services.audit_service import log_audit_event


router = APIRouter(
    prefix="/api/platform",
    tags=["platform"]
)


class OrganizationPlanUpdate(BaseModel):
    plan: Optional[str] = None
    billing_cycle: Optional[str] = None
    plan_status: Optional[str] = None


@router.get("/organizations")
def list_organizations(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_platform_admin)
):
    """
    Every organization on the platform, with real (non-demo) resource
    counts, plan/billing status, last authenticated activity, and
    today's Ask usage against that org's daily cap - the "who's using
    this and what are they doing" view for 100+ demo/trial signups.
    """

    return platform_service.list_organizations(db)


@router.get("/organizations/{organization_id}")
def get_organization(
    organization_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_platform_admin)
):

    detail = platform_service.get_organization_detail(db, organization_id)

    if detail is None:
        raise HTTPException(status_code=404, detail="Organization not found")

    return detail


@router.post("/organizations/{organization_id}/suspend")
def suspend_organization(
    organization_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_platform_admin)
):

    org = platform_service.set_organization_suspended(db, organization_id, True)

    if org is None:
        raise HTTPException(status_code=404, detail="Organization not found")

    log_audit_event(
        db,
        organization_id=organization_id,
        action="platform.suspend",
        actor_user_id=current_user.id,
        actor_email=current_user.email,
        resource_type="organization",
        resource_id=organization_id,
        details=f"Suspended by platform admin {current_user.email}",
    )
    db.commit()

    return {"message": "Organization suspended", "id": org.id, "is_suspended": org.is_suspended}


@router.post("/organizations/{organization_id}/activate")
def activate_organization(
    organization_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_platform_admin)
):

    org = platform_service.set_organization_suspended(db, organization_id, False)

    if org is None:
        raise HTTPException(status_code=404, detail="Organization not found")

    log_audit_event(
        db,
        organization_id=organization_id,
        action="platform.activate",
        actor_user_id=current_user.id,
        actor_email=current_user.email,
        resource_type="organization",
        resource_id=organization_id,
        details=f"Reactivated by platform admin {current_user.email}",
    )
    db.commit()

    return {"message": "Organization reactivated", "id": org.id, "is_suspended": org.is_suspended}


@router.patch("/organizations/{organization_id}/plan")
def update_organization_plan(
    organization_id: str,
    payload: OrganizationPlanUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_platform_admin)
):
    """
    Manual plan override - for Enterprise/custom deals closed by
    sales rather than run through self-serve Stripe checkout (see
    app/api/billing.py for that path).
    """

    org = platform_service.set_organization_plan(
        db,
        organization_id,
        plan=payload.plan,
        billing_cycle=payload.billing_cycle,
        plan_status=payload.plan_status,
    )

    if org is None:
        raise HTTPException(status_code=404, detail="Organization not found")

    log_audit_event(
        db,
        organization_id=organization_id,
        action="platform.plan_override",
        actor_user_id=current_user.id,
        actor_email=current_user.email,
        resource_type="organization",
        resource_id=organization_id,
        details=(
            f"Plan set to {org.plan}/{org.billing_cycle}/{org.plan_status} "
            f"by platform admin {current_user.email}"
        ),
    )
    db.commit()

    return {
        "message": "Plan updated",
        "id": org.id,
        "plan": org.plan,
        "billing_cycle": org.billing_cycle,
        "plan_status": org.plan_status,
    }


@router.get("/marketing/funnel")
def marketing_funnel(
    days: int = 30,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_platform_admin)
):
    """
    Website visitor -> signup funnel: pageviews, unique visitors,
    signups started/completed, and where completed signups came from
    (utm_source) - see app/api/marketing.py for how these events get
    written from the public marketing site.
    """

    return platform_service.marketing_funnel(db, days=days)
