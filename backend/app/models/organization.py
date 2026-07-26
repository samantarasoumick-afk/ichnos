import uuid

from sqlalchemy import Boolean
from sqlalchemy import Column
from sqlalchemy import DateTime
from sqlalchemy import String

from datetime import datetime

from sqlalchemy.orm import relationship

from app.db.database import Base


class Organization(Base):

    __tablename__ = "organizations"

    id = Column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4())
    )

    name = Column(
        String,
        nullable=False
    )

    slug = Column(
        String,
        unique=True,
        nullable=False
    )

    created_at = Column(
        DateTime,
        default=datetime.utcnow
    )

    # --- Billing / entitlements -------------------------------------
    # Every signup starts on "starter" (the free tier) - see
    # app/services/entitlements.py for what each plan actually caps
    # and gates. This is the single source of truth the rest of the
    # app checks against; nothing here implies payment has happened
    # (plan_status covers that).
    plan = Column(
        String,
        default="starter",
        nullable=False
    )

    # monthly / yearly / custom. "custom" covers Enterprise deals
    # closed by sales rather than self-serve Stripe checkout - see
    # app/services/billing_service.py.
    billing_cycle = Column(
        String,
        nullable=True
    )

    # trialing (default - free tier, never charged) / active (paid,
    # in good standing) / past_due (payment failed, Stripe retrying) /
    # canceled (subscription ended - entitlements fall back to
    # starter caps, but the org and its data are untouched).
    plan_status = Column(
        String,
        default="trialing",
        nullable=False
    )

    # A platform-admin kill switch, independent of plan/billing -
    # for abuse or a trial that's run its course. Checked in
    # app/auth/dependencies.py so a suspended org's users simply can't
    # authenticate against the API until lifted; nothing is deleted.
    is_suspended = Column(
        Boolean,
        default=False,
        nullable=False
    )

    stripe_customer_id = Column(
        String,
        unique=True,
        nullable=True
    )

    stripe_subscription_id = Column(
        String,
        unique=True,
        nullable=True
    )

    users = relationship(
        "User",
        back_populates="organization"
    )
