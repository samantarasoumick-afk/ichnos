"""
Admin-facing view over the query log (app/services/query_log_service.py)
- what's being asked on the Ask page and typed into the global search
bar, and specifically what isn't landing. Restricted to admins: unlike
the Audit Log, which is org-wide activity every teammate can
reasonably see, this exposes the literal text of what people searched
for, which can include sensitive-sounding phrasing even when nothing
was found.
"""

from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter
from fastapi import Depends
from fastapi import Query

from sqlalchemy.orm import Session

from app.db.session import get_db

from app.models.query_log import QueryLog
from app.models.user import User

from app.schemas.query_log import QueryLogEntry
from app.schemas.query_log import QueryLogReport

from app.auth.dependencies import require_role

from app.services.query_log_service import build_query_log_report


router = APIRouter(prefix="/api/query-log", tags=["query-log"])


def _apply_filters(query, source, matched, q, date_from, date_to):
    if source:
        query = query.filter(QueryLog.source == source)
    if matched is not None:
        query = query.filter(QueryLog.matched == matched)
    if q:
        query = query.filter(QueryLog.query_text.ilike(f"%{q}%"))
    if date_from:
        try:
            parsed_from = datetime.fromisoformat(date_from)
            query = query.filter(QueryLog.created_at >= parsed_from)
        except ValueError:
            pass
    if date_to:
        try:
            parsed_to = datetime.fromisoformat(date_to)
            if len(date_to) <= 10:
                parsed_to = parsed_to + timedelta(days=1)
            query = query.filter(QueryLog.created_at < parsed_to)
        except ValueError:
            pass
    return query


@router.get("", response_model=list[QueryLogEntry])
@router.get("/", response_model=list[QueryLogEntry])
def list_query_log(
    limit: int = Query(default=100, le=2000),
    source: Optional[str] = None,
    matched: Optional[bool] = None,
    q: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin")),
):
    query = db.query(QueryLog).filter(
        QueryLog.organization_id == current_user.organization_id
    )
    query = _apply_filters(query, source, matched, q, date_from, date_to)
    return query.order_by(QueryLog.created_at.desc()).limit(limit).all()


@router.get("/report", response_model=QueryLogReport)
@router.get("/report/", response_model=QueryLogReport)
def query_log_report(
    days: int = Query(default=30, ge=1, le=365),
    limit: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin")),
):
    return build_query_log_report(db, current_user.organization_id, days=days, limit=limit)
