"""
Self-serve Stripe billing for Team/Business - checkout, the hosted
customer portal, and webhook handling that flips an org's plan the
moment payment actually succeeds. Enterprise/custom stays sales-
assisted (a platform admin sets it by hand - see
app/services/platform_service.set_organization_plan) rather than
running through checkout here, matching the pricing page's own
"Talk to sales" framing for that tier.

Raw HTTP via `requests` against Stripe's REST API rather than the
`stripe` SDK - same minimal-dependency convention
app/services/assistant_service.py already uses for the Anthropic API.
Every function here degrades gracefully (returns None / raises a
clear, catchable error) when STRIPE_SECRET_KEY isn't set, so a
self-hosted instance that never configures Stripe keeps working
normally - it just can't run self-serve checkout, and stays on manual
plan overrides via the platform admin API.
"""

import hashlib
import hmac
import os
import time

import requests

from sqlalchemy.orm import Session

from app.models.organization import Organization


STRIPE_API_BASE = "https://api.stripe.com/v1"

# (plan, billing_cycle) -> the env var holding that Stripe Price id.
# Enterprise/custom deliberately has no entry here - see this
# module's docstring.
_PRICE_ENV_VARS = {
    ("team", "monthly"): "STRIPE_PRICE_TEAM_MONTHLY",
    ("team", "yearly"): "STRIPE_PRICE_TEAM_YEARLY",
    ("business", "monthly"): "STRIPE_PRICE_BUSINESS_MONTHLY",
    ("business", "yearly"): "STRIPE_PRICE_BUSINESS_YEARLY",
}


class BillingNotConfiguredError(Exception):
    """STRIPE_SECRET_KEY (or the relevant price id) isn't set."""
    pass


class BillingRequestError(Exception):
    """Stripe reachable, but rejected or failed the request."""
    pass


def is_configured() -> bool:
    return bool(os.getenv("STRIPE_SECRET_KEY"))


def _price_id_for(plan: str, billing_cycle: str) -> str:
    env_var = _PRICE_ENV_VARS.get((plan, billing_cycle))

    if env_var is None:
        raise BillingNotConfiguredError(
            f"No self-serve Stripe price for plan={plan!r}, "
            f"billing_cycle={billing_cycle!r}. Enterprise/custom plans "
            "are set manually by a platform admin instead."
        )

    price_id = os.getenv(env_var)

    if not price_id:
        raise BillingNotConfiguredError(
            f"{env_var} is not set - see .env.example. Self-serve "
            f"checkout for plan={plan!r}/{billing_cycle!r} isn't "
            "available until it is."
        )

    return price_id


def _stripe_post(path: str, data: dict) -> dict:
    api_key = os.getenv("STRIPE_SECRET_KEY")

    if not api_key:
        raise BillingNotConfiguredError(
            "STRIPE_SECRET_KEY is not set - see .env.example."
        )

    # Stripe's REST API takes application/x-www-form-urlencoded,
    # including bracket-nested keys for nested params (e.g.
    # "line_items[0][price]") - callers pass those keys pre-flattened.
    response = requests.post(
        f"{STRIPE_API_BASE}/{path}",
        auth=(api_key, ""),
        data=data,
        timeout=15,
    )

    if response.status_code >= 400:
        try:
            detail = response.json().get("error", {}).get("message", response.text)
        except ValueError:
            detail = response.text
        raise BillingRequestError(f"Stripe {path} failed: {detail}")

    return response.json()


def _ensure_stripe_customer(db: Session, organization: Organization, email: str) -> str:
    if organization.stripe_customer_id:
        return organization.stripe_customer_id

    customer = _stripe_post(
        "customers",
        {
            "email": email,
            "name": organization.name,
            "metadata[organization_id]": organization.id,
        },
    )

    organization.stripe_customer_id = customer["id"]
    db.commit()

    return customer["id"]


def create_checkout_session(
    db: Session,
    organization: Organization,
    plan: str,
    billing_cycle: str,
    admin_email: str,
    success_url: str,
    cancel_url: str,
) -> str:
    """
    Returns the Stripe-hosted Checkout URL to redirect the admin to.
    Reuses an existing Stripe customer if this org already has one
    (e.g. upgrading from Team to Business), otherwise creates one.
    """

    if not is_configured():
        raise BillingNotConfiguredError(
            "STRIPE_SECRET_KEY is not set - see .env.example. Self-serve "
            "billing isn't available on this instance; plan changes need "
            "a platform admin's manual override instead."
        )

    price_id = _price_id_for(plan, billing_cycle)
    customer_id = _ensure_stripe_customer(db, organization, admin_email)

    session = _stripe_post(
        "checkout/sessions",
        {
            "mode": "subscription",
            "customer": customer_id,
            "line_items[0][price]": price_id,
            "line_items[0][quantity]": 1,
            "success_url": success_url,
            "cancel_url": cancel_url,
            "metadata[organization_id]": organization.id,
            "metadata[plan]": plan,
            "metadata[billing_cycle]": billing_cycle,
            "subscription_data[metadata][organization_id]": organization.id,
        },
    )

    return session["url"]


def create_billing_portal_session(organization: Organization, return_url: str) -> str:
    """
    Stripe's hosted self-serve portal - update payment method, switch
    Team<->Business, view invoices, or cancel. Requires the org to
    already have a Stripe customer (i.e. has checked out at least
    once); callers should show "Upgrade" instead of a portal link
    until then.
    """

    if not is_configured():
        raise BillingNotConfiguredError(
            "STRIPE_SECRET_KEY is not set - see .env.example. Self-serve "
            "billing isn't available on this instance; plan changes need "
            "a platform admin's manual override instead."
        )

    if not organization.stripe_customer_id:
        raise BillingRequestError(
            "This organization has no Stripe customer yet - it needs "
            "to complete checkout at least once before the billing "
            "portal is available."
        )

    session = _stripe_post(
        "billing_portal/sessions",
        {
            "customer": organization.stripe_customer_id,
            "return_url": return_url,
        },
    )

    return session["url"]


def verify_webhook_signature(
    payload: bytes, signature_header: str, tolerance_seconds: int = 300
) -> bool:
    """
    Re-implements Stripe's own webhook signature check (normally
    `stripe.Webhook.construct_event`) by hand, since this module
    avoids the SDK - see this file's docstring. Stripe-Signature looks
    like "t=<timestamp>,v1=<hex hmac>[,v1=<hex hmac>...]" (multiple
    v1 values appear during a signing-secret rotation); a match
    against any of them is valid.
    """

    webhook_secret = os.getenv("STRIPE_WEBHOOK_SECRET")

    if not webhook_secret:
        return False

    parts = dict(
        item.split("=", 1) for item in signature_header.split(",") if "=" in item
    )
    timestamp = parts.get("t")

    if not timestamp:
        return False

    if abs(time.time() - int(timestamp)) > tolerance_seconds:
        return False

    signed_payload = f"{timestamp}.{payload.decode('utf-8')}"
    expected = hmac.new(
        webhook_secret.encode("utf-8"), signed_payload.encode("utf-8"), hashlib.sha256
    ).hexdigest()

    # Collect every v1= value (there can be more than one during a
    # secret rotation), not just the first.
    candidate_signatures = [
        item.split("=", 1)[1]
        for item in signature_header.split(",")
        if item.startswith("v1=")
    ]

    return any(hmac.compare_digest(expected, candidate) for candidate in candidate_signatures)


def handle_webhook_event(db: Session, event: dict) -> None:
    """
    Dispatches a verified Stripe event to the right Organization
    update. Every branch is defensive about missing metadata/fields
    rather than raising - a malformed or unexpected event should be a
    no-op, not a 500 that makes Stripe retry forever.
    """

    event_type = event.get("type")
    data = event.get("data", {}).get("object", {})

    if event_type == "checkout.session.completed":
        organization_id = data.get("metadata", {}).get("organization_id")
        plan = data.get("metadata", {}).get("plan")
        billing_cycle = data.get("metadata", {}).get("billing_cycle")
        subscription_id = data.get("subscription")

        if not organization_id:
            return

        org = db.query(Organization).filter(Organization.id == organization_id).first()
        if org is None:
            return

        if plan:
            org.plan = plan
        if billing_cycle:
            org.billing_cycle = billing_cycle
        org.plan_status = "active"
        if subscription_id:
            org.stripe_subscription_id = subscription_id

        db.commit()
        return

    if event_type in ("customer.subscription.updated", "customer.subscription.deleted"):
        subscription_id = data.get("id")
        status = data.get("status")

        if not subscription_id:
            return

        org = (
            db.query(Organization)
            .filter(Organization.stripe_subscription_id == subscription_id)
            .first()
        )
        if org is None:
            return

        if event_type == "customer.subscription.deleted" or status == "canceled":
            org.plan_status = "canceled"
        elif status in ("active", "trialing"):
            org.plan_status = "active"
        elif status in ("past_due", "unpaid", "incomplete_expired"):
            org.plan_status = "past_due"

        db.commit()
        return
