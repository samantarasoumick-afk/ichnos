from typing import Optional

from fastapi import APIRouter
from fastapi import Depends
from fastapi import HTTPException

from sqlalchemy.orm import Session

from app.db.session import get_db

from app.models.dataset import Dataset
from app.models.governance_thread import GovernanceThread
from app.models.governance_thread import GovernanceThreadReply
from app.models.user import User

from app.schemas.governance_thread import GovernanceThreadCreate
from app.schemas.governance_thread import GovernanceThreadDetailResponse
from app.schemas.governance_thread import GovernanceThreadReplyCreate
from app.schemas.governance_thread import GovernanceThreadReplyResponse
from app.schemas.governance_thread import GovernanceThreadResolve
from app.schemas.governance_thread import GovernanceThreadResponse

from app.auth.dependencies import get_current_user
from app.services.audit_service import log_audit_event

from datetime import datetime


router = APIRouter(
    prefix="/api/discussions",
    tags=["discussions"]
)

VALID_THREAD_TYPES = ("QUESTION", "PROPOSAL", "ISSUE")


def _dataset_label(dataset: Optional[Dataset]) -> Optional[str]:

    if dataset is None:
        return None

    return f"{dataset.schema_name}.{dataset.name}"


def _to_response(thread: GovernanceThread) -> GovernanceThreadResponse:

    return GovernanceThreadResponse(
        id=thread.id,
        dataset_id=thread.dataset_id,
        dataset_label=_dataset_label(thread.dataset),
        thread_type=thread.thread_type,
        title=thread.title,
        body=thread.body,
        status=thread.status,
        created_by=thread.created_by,
        created_by_email=thread.author.email if thread.author else None,
        created_at=thread.created_at,
        resolved_by=thread.resolved_by,
        resolved_by_email=thread.resolver.email if thread.resolver else None,
        resolved_at=thread.resolved_at,
        resolution_note=thread.resolution_note,
        raised_for_user_id=thread.raised_for_user_id,
        raised_for_email=thread.raised_for.email if thread.raised_for else None,
        reply_count=len(thread.replies),
    )


def _to_reply_response(reply: GovernanceThreadReply) -> GovernanceThreadReplyResponse:

    return GovernanceThreadReplyResponse(
        id=reply.id,
        thread_id=reply.thread_id,
        body=reply.body,
        created_by=reply.created_by,
        created_by_email=reply.author.email if reply.author else None,
        created_at=reply.created_at,
    )


def _to_detail_response(thread: GovernanceThread) -> GovernanceThreadDetailResponse:

    base = _to_response(thread)

    return GovernanceThreadDetailResponse(
        **base.model_dump(),
        replies=[_to_reply_response(reply) for reply in thread.replies],
    )


def _get_thread_or_404(thread_id: str, db: Session, current_user: User) -> GovernanceThread:

    thread = (
        db.query(GovernanceThread)
        .filter(
            GovernanceThread.id == thread_id,
            GovernanceThread.organization_id == current_user.organization_id
        )
        .first()
    )

    if not thread:

        raise HTTPException(
            status_code=404,
            detail="Discussion thread not found"
        )

    return thread


@router.get(
    "",
    response_model=list[GovernanceThreadResponse]
)
@router.get(
    "/",
    response_model=list[GovernanceThreadResponse]
)
def list_threads(
    dataset_id: Optional[str] = None,
    status: Optional[str] = None,
    thread_type: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):

    query = (
        db.query(GovernanceThread)
        .filter(GovernanceThread.organization_id == current_user.organization_id)
    )

    if dataset_id:
        query = query.filter(GovernanceThread.dataset_id == dataset_id)

    if status:
        query = query.filter(GovernanceThread.status == status.upper())

    if thread_type:
        query = query.filter(GovernanceThread.thread_type == thread_type.upper())

    threads = query.order_by(GovernanceThread.created_at.desc()).all()

    return [_to_response(thread) for thread in threads]


@router.post(
    "",
    response_model=GovernanceThreadDetailResponse
)
@router.post(
    "/",
    response_model=GovernanceThreadDetailResponse
)
def create_thread(
    payload: GovernanceThreadCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):

    thread_type = payload.thread_type.upper()

    if thread_type not in VALID_THREAD_TYPES:

        raise HTTPException(
            status_code=400,
            detail=f"thread_type must be one of {VALID_THREAD_TYPES}"
        )

    dataset = None

    if payload.dataset_id:

        dataset = (
            db.query(Dataset)
            .filter(
                Dataset.id == str(payload.dataset_id),
                Dataset.organization_id == current_user.organization_id
            )
            .first()
        )

        if not dataset:

            raise HTTPException(
                status_code=404,
                detail="Dataset not found"
            )

    raised_for = None

    if payload.raised_for_user_id:

        raised_for = (
            db.query(User)
            .filter(
                User.id == str(payload.raised_for_user_id),
                User.organization_id == current_user.organization_id
            )
            .first()
        )

        if not raised_for:

            raise HTTPException(
                status_code=404,
                detail="That stakeholder wasn't found in your organization"
            )

    thread = GovernanceThread(
        organization_id=current_user.organization_id,
        dataset_id=dataset.id if dataset else None,
        thread_type=thread_type,
        title=payload.title,
        body=payload.body,
        status="OPEN",
        created_by=current_user.id,
        raised_for_user_id=raised_for.id if raised_for else None,
    )

    db.add(thread)
    db.flush()

    log_audit_event(
        db,
        organization_id=current_user.organization_id,
        action="discussion.create",
        actor_user_id=current_user.id,
        actor_email=current_user.email,
        resource_type="governance_thread",
        resource_id=thread.id,
        details=f"Opened {thread_type.lower()} '{payload.title}'"
                + (f" on {_dataset_label(dataset)}" if dataset else "")
                + (f" - raised for {raised_for.email}" if raised_for else ""),
    )

    db.commit()
    db.refresh(thread)

    return _to_detail_response(thread)


@router.get(
    "/{thread_id}",
    response_model=GovernanceThreadDetailResponse
)
def get_thread(
    thread_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):

    thread = _get_thread_or_404(thread_id, db, current_user)

    return _to_detail_response(thread)


@router.post(
    "/{thread_id}/replies",
    response_model=GovernanceThreadDetailResponse
)
def add_reply(
    thread_id: str,
    payload: GovernanceThreadReplyCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):

    thread = _get_thread_or_404(thread_id, db, current_user)

    reply = GovernanceThreadReply(
        thread_id=thread.id,
        body=payload.body,
        created_by=current_user.id,
    )

    db.add(reply)

    log_audit_event(
        db,
        organization_id=current_user.organization_id,
        action="discussion.reply",
        actor_user_id=current_user.id,
        actor_email=current_user.email,
        resource_type="governance_thread",
        resource_id=thread.id,
        details=f"Replied to '{thread.title}'",
    )

    db.commit()
    db.refresh(thread)

    return _to_detail_response(thread)


@router.post(
    "/{thread_id}/resolve",
    response_model=GovernanceThreadDetailResponse
)
def resolve_thread(
    thread_id: str,
    payload: GovernanceThreadResolve,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):

    thread = _get_thread_or_404(thread_id, db, current_user)

    if thread.status == "RESOLVED":

        raise HTTPException(
            status_code=400,
            detail="This thread is already resolved."
        )

    # Anyone can raise a question or proposal, but only the person who
    # opened it - or a steward/admin who can speak for the org's
    # governance decisions - can mark it resolved. Otherwise any
    # participant could unilaterally close someone else's open
    # question.
    can_resolve = (
        thread.created_by == current_user.id
        or current_user.role in ("admin", "steward")
    )

    if not can_resolve:

        raise HTTPException(
            status_code=403,
            detail="Only the thread's author, a steward, or an admin can resolve it."
        )

    thread.status = "RESOLVED"
    thread.resolved_by = current_user.id
    thread.resolved_at = datetime.utcnow()
    thread.resolution_note = payload.resolution_note

    log_audit_event(
        db,
        organization_id=current_user.organization_id,
        action="discussion.resolve",
        actor_user_id=current_user.id,
        actor_email=current_user.email,
        resource_type="governance_thread",
        resource_id=thread.id,
        details=f"Resolved '{thread.title}'",
    )

    db.commit()
    db.refresh(thread)

    return _to_detail_response(thread)
