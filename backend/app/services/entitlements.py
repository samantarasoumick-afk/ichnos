"""
Single source of truth for what each pricing tier actually gets -
mirrors website/index.html's pricing cards. Nothing charges anyone;
this module only answers "is X allowed for this org's plan" so the
rest of the app (source creation, invites, the Ask assistant, feature
gates) can check a plan without hardcoding tier logic everywhere.

Two different kinds of limit live here, and they're enforced
differently on purpose:

- max_sources / ask_daily_limit are HARD caps on every plan,
  including paid ones - going over isn't a billing event, it's
  either a real product ceiling (sources) or a cost-control ceiling
  (Ask/LLM calls) that a plan bump raises rather than removes.
- max_editor_seats is only a hard block on the free "starter" plan.
  Team and Business both sell overage seats ($15/seat and $12/seat -
  see the pricing page) rather than blocking the invite, so exceeding
  the included count on a paid plan is allowed here and left for
  Stripe metered billing to actually charge for later - blocking a
  paying customer's invite because they're one seat over what shipped
  with their tier would be a worse outcome than under-billing them
  for a cycle.

Feature flags (column_lineage, dq_scoring, glossary, processes,
contracts, data_owner_role, maturity_dashboard, csv_export_audit) are
informational today - see app/services/entitlements.py's
is_feature_enabled() for the one place that would need to change if/
when any of these becomes an actual hard gate in the UI/API rather
than just a pricing-page promise.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.organization import Organization


PLANS = ("starter", "team", "business", "enterprise")


@dataclass(frozen=True)
class PlanEntitlements:
    plan: str
    max_sources: Optional[int]
    max_editor_seats: Optional[int]
    seats_hard_capped: bool
    ask_daily_limit: Optional[int]
    audit_log_retention_days: Optional[int]
    column_lineage: bool
    dq_scoring: bool
    glossary: bool
    processes: bool
    contracts: bool
    data_owner_role: bool
    maturity_dashboard: bool
    csv_export_audit: bool


_ENTITLEMENTS = {
    "starter": PlanEntitlements(
        plan="starter",
        max_sources=1,
        max_editor_seats=1,
        seats_hard_capped=True,
        ask_daily_limit=20,
        audit_log_retention_days=7,
        column_lineage=False,
        dq_scoring=False,
        glossary=False,
        processes=False,
        contracts=False,
        data_owner_role=False,
        maturity_dashboard=False,
        csv_export_audit=False,
    ),
    "team": PlanEntitlements(
        plan="team",
        max_sources=5,
        max_editor_seats=5,
        seats_hard_capped=False,
        ask_daily_limit=100,
        audit_log_retention_days=30,
        column_lineage=True,
        dq_scoring=True,
        glossary=True,
        processes=True,
        contracts=True,
        data_owner_role=False,
        maturity_dashboard=False,
        csv_export_audit=False,
    ),
    "business": PlanEntitlements(
        plan="business",
        max_sources=20,
        max_editor_seats=20,
        seats_hard_capped=False,
        ask_daily_limit=500,
        audit_log_retention_days=None,
        column_lineage=True,
        dq_scoring=True,
        glossary=True,
        processes=True,
        contracts=True,
        data_owner_role=True,
        maturity_dashboard=True,
        csv_export_audit=True,
    ),
    "enterprise": PlanEntitlements(
        plan="enterprise",
        max_sources=None,
        max_editor_seats=None,
        seats_hard_capped=False,
        ask_daily_limit=None,
        audit_log_retention_days=None,
        column_lineage=True,
        dq_scoring=True,
        glossary=True,
        processes=True,
        contracts=True,
        data_owner_role=True,
        maturity_dashboard=True,
        csv_export_audit=True,
    ),
    # Not a real pricing tier - what an org gets while plan_status is
    # "trialing" (every org's default from signup until it either
    # subscribes or its trial lapses). Every source/dataset cap and
    # feature gate is open, same as Business, specifically so 100+
    # people can be handed the app for demo/evaluation and actually
    # see the full product - the whole point of the demo-data seeder
    # built earlier is to showcase every feature, and a 1-source
    # starter cap would make that impossible for a brand-new signup.
    # The one exception is ask_daily_limit: real Anthropic API spend
    # happens on every Ask call regardless of trial status, so that
    # stays capped (just more generously than starter) rather than
    # left open - see enforce_ask_limit.
    "trial": PlanEntitlements(
        plan="trial",
        max_sources=None,
        max_editor_seats=None,
        seats_hard_capped=False,
        ask_daily_limit=50,
        audit_log_retention_days=None,
        column_lineage=True,
        dq_scoring=True,
        glossary=True,
        processes=True,
        contracts=True,
        data_owner_role=True,
        maturity_dashboard=True,
        csv_export_audit=True,
    ),
}


def get_entitlements(plan: Optional[str]) -> PlanEntitlements:
    """
    Falls back to starter's (most restrictive) entitlements for an
    unrecognized or missing plan value - fails closed, not open, so a
    typo'd/blank plan column never silently grants paid-tier access.
    """

    return _ENTITLEMENTS.get(plan or "starter", _ENTITLEMENTS["starter"])


def effective_entitlements(organization: Organization) -> PlanEntitlements:
    """
    What an organization actually gets right now - branches on
    plan_status first, since that (not `plan`) is what's actually
    true about the org's relationship to billing:

    - "trialing" (the default from signup): open trial entitlements
      regardless of what `plan` is set to - evaluating the product
      shouldn't be capped down to starter's 1-source limit.
    - "active": the real caps for whatever `plan` they're actually
      paying for (or deliberately staying on starter, unpaid, past
      their trial - see billing_service for how a trial "converts").
    - "past_due" / "canceled": falls back to starter's caps - data
      stays untouched, but a lapsed subscription doesn't keep trial-
      level access indefinitely.
    """

    if organization.plan_status == "trialing":
        return _ENTITLEMENTS["trial"]

    if organization.plan_status in ("canceled", "past_due"):
        return _ENTITLEMENTS["starter"]

    return get_entitlements(organization.plan)


def is_feature_enabled(organization: Organization, feature: str) -> bool:
    entitlements = effective_entitlements(organization)
    return bool(getattr(entitlements, feature, False))


def enforce_source_limit(db: Session, current_user) -> None:
    """
    Raises 402 if creating one more source would exceed the org's
    plan. Called at the top of every source-creation endpoint
    (connectors, CSV upload, dbt upload, Tableau connect) in
    app/api/sources.py, before any work happens - so a blocked
    request never partially ingests anything.
    """

    from app.models.source import DataSource  # local import: avoid a
    # models -> services -> models import cycle at module load time.

    entitlements = effective_entitlements(current_user.organization)

    if entitlements.max_sources is None:
        return

    # Demo sources (loaded via the Demo Data panel) never count
    # against a real plan's cap - they're not "your data," they're a
    # disposable example estate meant to be cleared before connecting
    # anything real.
    current_count = (
        db.query(DataSource)
        .filter(
            DataSource.organization_id == current_user.organization_id,
            DataSource.is_seed_data.is_(False),
        )
        .count()
    )

    if current_count >= entitlements.max_sources:
        raise HTTPException(
            status_code=402,
            detail=(
                f"Your {entitlements.plan} plan includes "
                f"{entitlements.max_sources} connected source"
                f"{'s' if entitlements.max_sources != 1 else ''}. "
                "Upgrade your plan to connect more."
            ),
        )


def enforce_seat_limit(db: Session, current_user) -> None:
    """
    Raises 402 if inviting one more editor would exceed the org's
    plan - but only on plans where seats are a hard cap (starter,
    the free tier). Team/Business sell overage seats rather than
    blocking the invite - see this module's docstring.
    """

    from app.models.user import User  # local import, same reason as above

    entitlements = effective_entitlements(current_user.organization)

    if entitlements.max_editor_seats is None or not entitlements.seats_hard_capped:
        return

    current_count = (
        db.query(User)
        .filter(
            User.organization_id == current_user.organization_id,
            User.role != "viewer",
            User.is_active.is_(True),
        )
        .count()
    )

    if current_count >= entitlements.max_editor_seats:
        raise HTTPException(
            status_code=402,
            detail=(
                f"Your {entitlements.plan} plan includes "
                f"{entitlements.max_editor_seats} editor seat"
                f"{'s' if entitlements.max_editor_seats != 1 else ''} "
                "(Viewer seats are always free and unlimited). "
                "Upgrade your plan to add more editors."
            ),
        )


def enforce_ask_limit(db: Session, current_user) -> None:
    """
    The cost guard: raises 429 if this org has already used up its
    daily Ask-assistant allowance. Called in app/api/assistant.py
    before the Anthropic API is ever invoked, so a capped org's
    request fails fast and cheaply instead of after spending tokens.
    Counts today's QueryLog rows with source="ask" for this org -
    the same table the Search Insights report reads, so this doesn't
    need its own counter to stay in sync.
    """

    from app.models.query_log import QueryLog  # local import, same reason as above

    entitlements = effective_entitlements(current_user.organization)

    if entitlements.ask_daily_limit is None:
        return

    since = datetime.utcnow() - timedelta(hours=24)

    used_today = (
        db.query(QueryLog)
        .filter(
            QueryLog.organization_id == current_user.organization_id,
            QueryLog.source == "ask",
            QueryLog.created_at >= since,
        )
        .count()
    )

    if used_today >= entitlements.ask_daily_limit:
        raise HTTPException(
            status_code=429,
            detail=(
                f"Your {entitlements.plan} plan includes "
                f"{entitlements.ask_daily_limit} Ask'Fe' questions per day, "
                "and you've used all of them in the last 24 hours. "
                "Upgrade your plan for a higher daily limit, or try "
                "again tomorrow."
            ),
        )
