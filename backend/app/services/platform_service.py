"""
Cross-organization rollups for the platform admin dashboard - the one
place in the codebase allowed to query across every tenant at once.
Every other service/API in this app deliberately filters by
organization_id; this module exists specifically so DatFe's own
operator can see "who's using this thing" across 100+ demo/trial
orgs without logging into each one individually. Gated entirely by
require_platform_admin (app/auth/dependencies.py) - nothing here is
reachable by an org-scoped admin.
"""

from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.audit_log import AuditLog
from app.models.dataset import Dataset
from app.models.marketing_event import MarketingEvent
from app.models.organization import Organization
from app.models.query_log import QueryLog
from app.models.source import DataSource
from app.models.user import User

from app.services.entitlements import effective_entitlements


# Every successful sign-in, regardless of method, writes one of these
# to audit_logs (see app/api/auth.py) - this module just rolls them up
# across every tenant rather than adding any new tracking.
LOGIN_ACTIONS = [
    "user.login",
    "user.magic_link_login",
    "user.github_login",
    "user.github_register",
]

LOGIN_METHOD_LABELS = {
    "user.login": "Password",
    "user.magic_link_login": "Magic link",
    "user.github_login": "GitHub",
    "user.github_register": "GitHub (signup)",
}


def _last_activity_by_org(db: Session) -> dict:
    rows = (
        db.query(AuditLog.organization_id, func.max(AuditLog.created_at))
        .group_by(AuditLog.organization_id)
        .all()
    )
    return {org_id: last_seen for org_id, last_seen in rows}


def _counts_by_org(db: Session, model, extra_filter=None) -> dict:
    query = db.query(model.organization_id, func.count(model.id))
    if extra_filter is not None:
        query = query.filter(extra_filter)
    rows = query.group_by(model.organization_id).all()
    return {org_id: count for org_id, count in rows}


def list_organizations(db: Session) -> list[dict]:
    """
    One row per organization with everything a platform admin needs
    to answer "who's actually using this, and who's gone cold" -
    signup date, plan/billing status, real (non-demo) resource
    counts, demo-data status, last authenticated activity, and
    today's Ask usage against that org's daily cap.
    """

    orgs = db.query(Organization).order_by(Organization.created_at.desc()).all()

    last_activity = _last_activity_by_org(db)
    real_source_counts = _counts_by_org(db, DataSource, DataSource.is_seed_data.is_(False))
    seed_source_counts = _counts_by_org(db, DataSource, DataSource.is_seed_data.is_(True))
    dataset_counts = _counts_by_org(db, Dataset)
    editor_seat_counts = _counts_by_org(
        db, User,
        (User.role != "viewer") & (User.is_active.is_(True)) & (User.is_seed_data.is_(False)),
    )

    since = datetime.utcnow() - timedelta(hours=24)
    ask_usage_rows = (
        db.query(QueryLog.organization_id, func.count(QueryLog.id))
        .filter(QueryLog.source == "ask", QueryLog.created_at >= since)
        .group_by(QueryLog.organization_id)
        .all()
    )
    ask_usage_today = {org_id: count for org_id, count in ask_usage_rows}

    results = []

    for org in orgs:
        entitlements = effective_entitlements(org)

        results.append({
            "id": org.id,
            "name": org.name,
            "slug": org.slug,
            "created_at": org.created_at,
            "plan": org.plan,
            "billing_cycle": org.billing_cycle,
            "plan_status": org.plan_status,
            "is_suspended": org.is_suspended,
            "real_source_count": real_source_counts.get(org.id, 0),
            "demo_data_loaded": seed_source_counts.get(org.id, 0) > 0,
            "dataset_count": dataset_counts.get(org.id, 0),
            "editor_seat_count": editor_seat_counts.get(org.id, 0),
            "last_activity_at": last_activity.get(org.id),
            "ask_usage_today": ask_usage_today.get(org.id, 0),
            "ask_daily_limit": entitlements.ask_daily_limit,
            "max_sources": entitlements.max_sources,
        })

    return results


def list_user_logins(db: Session) -> list[dict]:
    """
    "Who logged in" - one row per user who has ever authenticated,
    across every organization, with a running login count, first/last
    seen, and the method of their most recent login. Phase 1 of the
    superadmin monitoring view; failed-login/lockout activity, support
    issues, and billing compliance are separate, later phases (billing
    compliance is already partially visible today via each
    organization's plan_status in list_organizations - "past_due"
    orgs stand out there).

    Built entirely from existing audit_logs rows rather than a new
    table - the same rows _last_activity_by_org above already reads,
    just grouped by user instead of by org.
    """

    events = (
        db.query(AuditLog, User, Organization)
        .join(User, User.id == AuditLog.actor_user_id)
        .join(Organization, Organization.id == User.organization_id)
        .filter(AuditLog.action.in_(LOGIN_ACTIONS))
        .order_by(AuditLog.created_at.desc())
        .all()
    )

    # Walking newest -> oldest per the query's ORDER BY: the first row
    # seen for a given user is necessarily their most recent login, and
    # whatever row is seen last for them (the oldest) ends up as
    # first_login_at once the loop finishes.
    by_user: dict = {}

    for log, user, org in events:
        entry = by_user.get(user.id)

        if entry is None:
            entry = {
                "user_id": user.id,
                "email": user.email,
                "role": user.role,
                "is_seed_data": user.is_seed_data,
                "organization_id": org.id,
                "organization_name": org.name,
                "login_count": 0,
                "first_login_at": log.created_at,
                "last_login_at": log.created_at,
                "last_login_method": LOGIN_METHOD_LABELS.get(log.action, log.action),
            }
            by_user[user.id] = entry

        entry["login_count"] += 1
        entry["first_login_at"] = log.created_at

    return sorted(by_user.values(), key=lambda entry: entry["last_login_at"], reverse=True)


def get_organization_detail(db: Session, organization_id: str) -> Optional[dict]:
    org = db.query(Organization).filter(Organization.id == organization_id).first()

    if org is None:
        return None

    entitlements = effective_entitlements(org)

    members = (
        db.query(User)
        .filter(User.organization_id == organization_id)
        .order_by(User.created_at.asc())
        .all()
    )

    since = datetime.utcnow() - timedelta(hours=24)
    ask_usage_today = (
        db.query(QueryLog)
        .filter(
            QueryLog.organization_id == organization_id,
            QueryLog.source == "ask",
            QueryLog.created_at >= since,
        )
        .count()
    )

    real_source_count = (
        db.query(DataSource)
        .filter(
            DataSource.organization_id == organization_id,
            DataSource.is_seed_data.is_(False),
        )
        .count()
    )

    demo_data_loaded = (
        db.query(DataSource)
        .filter(
            DataSource.organization_id == organization_id,
            DataSource.is_seed_data.is_(True),
        )
        .first()
        is not None
    )

    recent_activity = (
        db.query(AuditLog)
        .filter(AuditLog.organization_id == organization_id)
        .order_by(AuditLog.created_at.desc())
        .limit(20)
        .all()
    )

    return {
        "id": org.id,
        "name": org.name,
        "slug": org.slug,
        "created_at": org.created_at,
        "plan": org.plan,
        "billing_cycle": org.billing_cycle,
        "plan_status": org.plan_status,
        "is_suspended": org.is_suspended,
        "stripe_customer_id": org.stripe_customer_id,
        "real_source_count": real_source_count,
        "max_sources": entitlements.max_sources,
        "demo_data_loaded": demo_data_loaded,
        "ask_usage_today": ask_usage_today,
        "ask_daily_limit": entitlements.ask_daily_limit,
        "members": [
            {
                "id": member.id,
                "email": member.email,
                "role": member.role,
                "is_active": member.is_active,
                "is_seed_data": member.is_seed_data,
            }
            for member in members
        ],
        "recent_activity": [
            {
                "action": entry.action,
                "actor_email": entry.actor_email,
                "details": entry.details,
                "created_at": entry.created_at,
            }
            for entry in recent_activity
        ],
    }


def marketing_funnel(db: Session, days: int = 30) -> dict:
    """
    Website visitor -> signup funnel over a trailing window, plus a
    breakdown of where signups came from - the "who are the visitors,
    what demos are being signed up" half of the platform dashboard.
    """

    since = datetime.utcnow() - timedelta(days=days)

    base = db.query(MarketingEvent).filter(MarketingEvent.created_at >= since)

    pageviews = base.filter(MarketingEvent.event_type == "pageview").count()
    unique_visitors = (
        db.query(func.count(func.distinct(MarketingEvent.anon_id)))
        .filter(MarketingEvent.created_at >= since, MarketingEvent.event_type == "pageview")
        .scalar()
    ) or 0
    signups_started = base.filter(MarketingEvent.event_type == "signup_started").count()
    signups_completed = base.filter(MarketingEvent.event_type == "signup_completed").count()

    by_source_rows = (
        db.query(MarketingEvent.utm_source, func.count(MarketingEvent.id))
        .filter(
            MarketingEvent.created_at >= since,
            MarketingEvent.event_type == "signup_completed",
        )
        .group_by(MarketingEvent.utm_source)
        .all()
    )

    conversion_rate = (
        round(100 * signups_completed / unique_visitors, 1) if unique_visitors else 0.0
    )

    return {
        "window_days": days,
        "pageviews": pageviews,
        "unique_visitors": unique_visitors,
        "signups_started": signups_started,
        "signups_completed": signups_completed,
        "visitor_to_signup_rate": conversion_rate,
        "signups_by_source": [
            {"utm_source": source or "direct", "count": count}
            for source, count in by_source_rows
        ],
    }


def set_organization_plan(
    db: Session,
    organization_id: str,
    plan: Optional[str],
    billing_cycle: Optional[str],
    plan_status: Optional[str],
) -> Optional[Organization]:
    """
    Manual override for sales-closed deals (Enterprise/custom, or any
    plan a platform admin sets by hand rather than through self-serve
    Stripe checkout - see app/api/billing.py for the self-serve path).
    """

    org = db.query(Organization).filter(Organization.id == organization_id).first()

    if org is None:
        return None

    if plan is not None:
        org.plan = plan
    if billing_cycle is not None:
        org.billing_cycle = billing_cycle
    if plan_status is not None:
        org.plan_status = plan_status

    db.commit()
    db.refresh(org)

    return org


def set_organization_suspended(
    db: Session, organization_id: str, suspended: bool
) -> Optional[Organization]:
    org = db.query(Organization).filter(Organization.id == organization_id).first()

    if org is None:
        return None

    org.is_suspended = suspended
    db.commit()
    db.refresh(org)

    return org
