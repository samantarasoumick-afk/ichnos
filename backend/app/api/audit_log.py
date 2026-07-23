import csv
import io
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter
from fastapi import Depends
from fastapi import Query
from fastapi.responses import StreamingResponse

from sqlalchemy.orm import Session

from app.db.session import get_db

from app.models.audit_log import AuditLog
from app.models.user import User

from app.schemas.audit_log import AuditLogResponse

from app.auth.dependencies import get_current_user


router = APIRouter(
    prefix="/api/audit-log",
    tags=["audit-log"]
)


def _apply_filters(
    query,
    action: Optional[str],
    actor: Optional[str],
    resource_type: Optional[str],
    date_from: Optional[str],
    date_to: Optional[str],
):
    """
    Shared filter logic for both the JSON listing and the CSV export -
    the two must always agree on what "filtered" means, so a steward
    exporting a filtered view gets exactly the rows they were just
    looking at, not a subtly different set.
    """

    if action:
        query = query.filter(AuditLog.action.ilike(f"%{action}%"))

    if actor:
        query = query.filter(AuditLog.actor_email.ilike(f"%{actor}%"))

    if resource_type:
        query = query.filter(AuditLog.resource_type.ilike(f"%{resource_type}%"))

    if date_from:
        try:
            parsed_from = datetime.fromisoformat(date_from)
            query = query.filter(AuditLog.created_at >= parsed_from)
        except ValueError:
            pass

    if date_to:
        try:
            # Treat a bare date as inclusive of the whole day.
            parsed_to = datetime.fromisoformat(date_to)
            if len(date_to) <= 10:
                parsed_to = parsed_to + timedelta(days=1)
            query = query.filter(AuditLog.created_at < parsed_to)
        except ValueError:
            pass

    return query


@router.get(
    "",
    response_model=list[AuditLogResponse]
)
@router.get(
    "/",
    response_model=list[AuditLogResponse]
)
def list_audit_log(
    limit: int = Query(default=100, le=2000),
    action: Optional[str] = None,
    actor: Optional[str] = None,
    resource_type: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):

    query = db.query(AuditLog).filter(
        AuditLog.organization_id == current_user.organization_id
    )

    query = _apply_filters(query, action, actor, resource_type, date_from, date_to)

    return (
        query
        .order_by(AuditLog.created_at.desc())
        .limit(limit)
        .all()
    )


@router.get("/export")
def export_audit_log(
    action: Optional[str] = None,
    actor: Optional[str] = None,
    resource_type: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Same filters as the listing endpoint, but returns every matching
    row (no page limit) as a CSV download - a steward reviewing a
    quarter's worth of activity shouldn't be capped at 500 rows.
    """

    query = db.query(AuditLog).filter(
        AuditLog.organization_id == current_user.organization_id
    )

    query = _apply_filters(query, action, actor, resource_type, date_from, date_to)

    entries = query.order_by(AuditLog.created_at.desc()).all()

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["created_at", "actor_email", "action", "resource_type", "resource_id", "details"])

    for entry in entries:
        writer.writerow([
            entry.created_at.isoformat() if entry.created_at else "",
            entry.actor_email or "",
            entry.action or "",
            entry.resource_type or "",
            entry.resource_id or "",
            entry.details or "",
        ])

    buffer.seek(0)

    filename = f"audit-log-{datetime.utcnow().strftime('%Y%m%d-%H%M%S')}.csv"

    return StreamingResponse(
        iter([buffer.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )
