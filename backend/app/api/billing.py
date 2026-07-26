import os

from fastapi import APIRouter
from fastapi import Depends
from fastapi import HTTPException
from fastapi import Request

from pydantic import BaseModel

from sqlalchemy.orm import Session

from app.db.session import get_db

from app.models.user import User

from app.auth.dependencies import get_current_user, require_role
from app.services import billing_service
from app.services.entitlements import effective_entitlements
from app.services.audit_service import log_audit_event


router = APIRouter(
    prefix="/api/billing",
    tags=["billing"]
)

FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:3000").rstrip("/")


class CheckoutRequest(BaseModel):
    plan: str
    billing_cycle: str


@router.get("/status")
def get_billing_status(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Current plan/status plus the entitlement caps that apply right
    now (see app/services/entitlements.py - a trialing org sees the
    open trial caps here, not its underlying starter plan's caps).
    Used by the frontend billing page and can double as a lightweight
    "am I limited" check anywhere else in the app.
    """

    org = current_user.organization
    entitlements = effective_entitlements(org)

    return {
        "plan": org.plan,
        "billing_cycle": org.billing_cycle,
        "plan_status": org.plan_status,
        "has_stripe_customer": bool(org.stripe_customer_id),
        "stripe_configured": billing_service.is_configured(),
        "entitlements": {
            "max_sources": entitlements.max_sources,
            "max_editor_seats": entitlements.max_editor_seats,
            "seats_hard_capped": entitlements.seats_hard_capped,
            "ask_daily_limit": entitlements.ask_daily_limit,
            "audit_log_retention_days": entitlements.audit_log_retention_days,
        },
    }


@router.post("/checkout")
def create_checkout(
    payload: CheckoutRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin"))
):
    """
    Self-serve upgrade for Team/Business, monthly or yearly. Not
    available for Enterprise/custom - those stay sales-assisted via a
    platform admin's manual override (app/api/platform.py's
    PATCH /organizations/{id}/plan), matching the pricing page's own
    "Talk to sales" framing.
    """

    org = current_user.organization

    try:
        checkout_url = billing_service.create_checkout_session(
            db,
            org,
            plan=payload.plan,
            billing_cycle=payload.billing_cycle,
            admin_email=current_user.email,
            success_url=f"{FRONTEND_URL}/settings/billing?checkout=success",
            cancel_url=f"{FRONTEND_URL}/settings/billing?checkout=canceled",
        )
    except billing_service.BillingNotConfiguredError as error:
        raise HTTPException(status_code=503, detail=str(error))
    except billing_service.BillingRequestError as error:
        raise HTTPException(status_code=502, detail=str(error))

    return {"checkout_url": checkout_url}


@router.post("/portal")
def create_portal_session(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin"))
):
    """
    Stripe's hosted self-serve portal - payment method, plan
    switching between Team/Business, invoices, cancellation.
    """

    org = current_user.organization

    try:
        portal_url = billing_service.create_billing_portal_session(
            org,
            return_url=f"{FRONTEND_URL}/settings/billing",
        )
    except billing_service.BillingNotConfiguredError as error:
        raise HTTPException(status_code=503, detail=str(error))
    except billing_service.BillingRequestError as error:
        raise HTTPException(status_code=400, detail=str(error))

    return {"portal_url": portal_url}


@router.post("/webhook")
async def stripe_webhook(
    request: Request,
    db: Session = Depends(get_db)
):
    """
    Public - Stripe calls this directly, so it can't require a bearer
    token. Authenticity instead comes from the Stripe-Signature header
    check (app/services/billing_service.verify_webhook_signature),
    which is why the raw request body is read and verified before the
    JSON is ever parsed or trusted.
    """

    raw_body = await request.body()
    signature_header = request.headers.get("stripe-signature", "")

    if not billing_service.verify_webhook_signature(raw_body, signature_header):
        raise HTTPException(status_code=400, detail="Invalid webhook signature")

    event = await request.json()

    billing_service.handle_webhook_event(db, event)

    organization_id = (
        event.get("data", {}).get("object", {}).get("metadata", {}).get("organization_id")
    )
    if organization_id:
        log_audit_event(
            db,
            organization_id=organization_id,
            action="billing.webhook",
            actor_user_id=None,
            actor_email="stripe-webhook",
            resource_type="organization",
            resource_id=organization_id,
            details=f"Stripe event {event.get('type')} processed",
        )
        db.commit()

    return {"received": True}
