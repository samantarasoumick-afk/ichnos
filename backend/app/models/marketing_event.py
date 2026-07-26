import uuid

from datetime import datetime

from sqlalchemy import Column
from sqlalchemy import DateTime
from sqlalchemy import ForeignKey
from sqlalchemy import String

from app.db.database import Base


class MarketingEvent(Base):
    """
    Website visitor + signup-funnel tracking - deliberately separate
    from AuditLog (a compliance trail of authenticated actions inside
    the app) and DatasetView (in-app usage). This table exists to
    answer "who's landing on the marketing site, what are they
    clicking, and which visits actually turn into a signup" - the
    question a public marketing page (website/index.html) needs
    answered before anyone has an account at all.

    Privacy note: rows are written from an unauthenticated public
    endpoint (POST /api/marketing/track), so nothing here stores an
    IP address or other directly-identifying value - anon_id is a
    random id generated client-side and kept in the visitor's
    browser (see website/index.html's tracking snippet), not a
    fingerprint. organization_id/user_id only get backfilled once a
    visit actually converts into a real signup (see
    app/api/auth.py's register()), which is what lets a platform
    admin trace "this org came from this visit" without ever needing
    to identify someone who never signed up.
    """

    __tablename__ = "marketing_events"

    id = Column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4())
    )

    # "pageview" / "cta_click" / "signup_started" / "signup_completed".
    # Free-text rather than an enum so the tracking snippet can add
    # new event names without a migration.
    event_type = Column(String, nullable=False, index=True)

    # Client-generated (crypto.randomUUID(), stored in localStorage by
    # the website) - identifies a returning visitor's browser across
    # events without identifying the person.
    anon_id = Column(String, nullable=False, index=True)

    path = Column(String, nullable=True)
    referrer = Column(String, nullable=True)

    utm_source = Column(String, nullable=True)
    utm_medium = Column(String, nullable=True)
    utm_campaign = Column(String, nullable=True)

    # Filled in retroactively (via anon_id match) the moment this
    # visitor's browser completes registration - see
    # marketing_service.link_anon_id_to_signup().
    organization_id = Column(
        String(36),
        ForeignKey("organizations.id"),
        nullable=True,
        index=True,
    )
    user_id = Column(
        String(36),
        ForeignKey("users.id"),
        nullable=True,
    )

    created_at = Column(DateTime, default=datetime.utcnow, nullable=True)
