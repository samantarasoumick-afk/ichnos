from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from app.models.marketing_event import MarketingEvent


# Free-text on the model (see MarketingEvent's docstring), but the
# tracking endpoint only accepts these - anything else is silently
# dropped rather than erroring, so a typo in a future snippet change
# never breaks the public marketing site.
ALLOWED_EVENT_TYPES = {"pageview", "cta_click", "signup_started", "signup_completed"}

_MAX_FIELD_LENGTH = 500


def _truncate(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    return value[:_MAX_FIELD_LENGTH]


def record_event(
    db: Session,
    event_type: str,
    anon_id: str,
    path: Optional[str] = None,
    referrer: Optional[str] = None,
    utm_source: Optional[str] = None,
    utm_medium: Optional[str] = None,
    utm_campaign: Optional[str] = None,
    organization_id: Optional[str] = None,
    user_id: Optional[str] = None,
) -> Optional[MarketingEvent]:
    """
    Deliberately does not commit - same reasoning as
    audit_service.log_audit_event: the caller (either the public
    /api/marketing/track endpoint, standalone, or register() as part
    of a larger signup transaction) decides when the write actually
    lands.
    """

    if event_type not in ALLOWED_EVENT_TYPES:
        return None

    if not anon_id or not anon_id.strip():
        return None

    event = MarketingEvent(
        event_type=event_type,
        anon_id=anon_id.strip()[:200],
        path=_truncate(path),
        referrer=_truncate(referrer),
        utm_source=_truncate(utm_source),
        utm_medium=_truncate(utm_medium),
        utm_campaign=_truncate(utm_campaign),
        organization_id=organization_id,
        user_id=user_id,
        created_at=datetime.utcnow(),
    )

    db.add(event)
    db.flush()

    return event


def link_anon_id_to_signup(
    db: Session, anon_id: Optional[str], organization_id: str, user_id: str
) -> None:
    """
    Called from app/api/auth.py's register() the moment a signup
    completes. Retroactively tags this visitor's earlier pageview/
    cta_click events with the organization they ended up creating -
    so "which visit led to this org" is answerable from the platform
    dashboard - then records the signup_completed event itself,
    which is what marketing_funnel() actually counts conversions
    from. A no-op if the frontend never had an anon_id to send (e.g.
    GitHub OAuth signup, or the website's tracking snippet was
    blocked) - conversion tracking is best-effort, never a signup
    requirement.
    """

    if not anon_id or not anon_id.strip():
        return

    anon_id = anon_id.strip()[:200]

    db.query(MarketingEvent).filter(MarketingEvent.anon_id == anon_id).update(
        {MarketingEvent.organization_id: organization_id}, synchronize_session=False
    )

    record_event(
        db,
        event_type="signup_completed",
        anon_id=anon_id,
        organization_id=organization_id,
        user_id=user_id,
    )
