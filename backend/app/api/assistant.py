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

    result = answer_question(db, current_user.organization_id, payload.query)

    return result
