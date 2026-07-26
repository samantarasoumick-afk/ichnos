from typing import Optional

from fastapi import APIRouter
from fastapi import Depends

from pydantic import BaseModel

from sqlalchemy.orm import Session

from app.db.session import get_db
from app.services import marketing_service


router = APIRouter(
    prefix="/api/marketing",
    tags=["marketing"]
)


class TrackEventRequest(BaseModel):
    event_type: str
    anon_id: str
    path: Optional[str] = None
    referrer: Optional[str] = None
    utm_source: Optional[str] = None
    utm_medium: Optional[str] = None
    utm_campaign: Optional[str] = None


@router.post("/track")
def track_event(
    payload: TrackEventRequest,
    db: Session = Depends(get_db)
):
    """
    Public, unauthenticated - called from website/index.html's
    tracking snippet on every pageview and CTA click, before anyone
    has an account. Deliberately quiet on rejection (unrecognized
    event_type, missing anon_id) rather than raising - a tracking
    call failing should never surface an error to a visitor who
    hasn't signed up yet. Covered by the same global per-IP rate
    limit as the rest of the API (app/middleware/rate_limit.py).
    """

    event = marketing_service.record_event(
        db,
        event_type=payload.event_type,
        anon_id=payload.anon_id,
        path=payload.path,
        referrer=payload.referrer,
        utm_source=payload.utm_source,
        utm_medium=payload.utm_medium,
        utm_campaign=payload.utm_campaign,
    )

    if event is not None:
        db.commit()

    return {"ok": True}
