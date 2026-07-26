"""
Powers the "@" mention picker: typing "@" in the Ask input or the
global search bar pops an autocomplete of catalog entities by name,
so a question or search can reference one precisely (its exact name
gets inserted into the text) instead of relying on the receiving
endpoint's own keyword/TF-IDF matching to land on the right one. This
is name-prefix lookup, not relevance search - see
catalog_search_service.list_mentionable()'s docstring for why that's
a different algorithm from /api/search's semantic_search().
"""

from fastapi import APIRouter
from fastapi import Depends
from fastapi import Query

from sqlalchemy.orm import Session

from app.db.session import get_db

from app.models.user import User

from app.schemas.mention import MentionItem
from app.schemas.mention import MentionResponse

from app.auth.dependencies import get_current_user

from app.services.catalog_search_service import describe_document
from app.services.catalog_search_service import list_mentionable


router = APIRouter(
    prefix="/api/mentions",
    tags=["mentions"]
)


@router.get("", response_model=MentionResponse)
def mentions(
    q: str = Query(default="", description="Partial entity name typed after @"),
    limit: int = Query(default=8, ge=1, le=20),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):

    documents = list_mentionable(db, current_user.organization_id, q, limit=limit)

    results = []

    for document in documents:
        subtitle, _url = describe_document(document)

        results.append(MentionItem(
            type=document.doc_type,
            id=document.id,
            label=document.label,
            subtitle=subtitle,
        ))

    return MentionResponse(results=results)
