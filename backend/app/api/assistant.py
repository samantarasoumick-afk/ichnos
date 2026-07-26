from fastapi import APIRouter
from fastapi import Depends
from fastapi import HTTPException

from sqlalchemy.orm import Session

from app.db.session import get_db

from app.models.user import User

from app.schemas.assistant import AskRequest
from app.schemas.assistant import AskResponse

from app.auth.dependencies import get_current_user
from app.services.assistant_service import answer_question
from app.services.query_log_service import classify_ask_answer
from app.services.query_log_service import log_query_event


router = APIRouter(
    prefix="/api/assistant",
    tags=["assistant"]
)


@router.post(
    "/ask",
    response_model=AskResponse
)
def ask(
    payload: AskRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):

    if not payload.query or not payload.query.strip():

        raise HTTPException(
            status_code=400,
            detail="Ask a question first."
        )

    history = [{"role": turn.role, "text": turn.text} for turn in payload.history]

    result = answer_question(db, current_user.organization_id, payload.query, history=history)

    log_query_event(
        db,
        organization_id=current_user.organization_id,
        source="ask",
        query_text=payload.query,
        matched=classify_ask_answer(result.get("answer", "")),
        actor_user_id=current_user.id,
        actor_email=current_user.email,
        result_count=len(result.get("sources", [])),
    )

    return result
