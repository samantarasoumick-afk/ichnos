"""
The app's global, cross-entity search bar (top nav "Search everything"
box) - not to be confused with the Ask assistant, which answers
questions in prose. This just finds things and links to them. Both
sit on top of the same TF-IDF retrieval in
app/services/catalog_search_service.py.
"""

from fastapi import APIRouter
from fastapi import Depends
from fastapi import Query

from sqlalchemy.orm import Session

from app.db.session import get_db

from app.models.user import User

from app.schemas.search import SearchResponse
from app.schemas.search import SearchResultItem

from app.auth.dependencies import get_current_user

from app.services.catalog_search_service import describe_document
from app.services.catalog_search_service import semantic_search
from app.services.query_log_service import log_query_event


router = APIRouter(
    prefix="/api/search",
    tags=["search"]
)

SNIPPET_MAX_LENGTH = 160


def _snippet(text: str, label: str) -> str:

    # The label itself is already shown prominently - strip it out of
    # the snippet if it's a prefix of the corpus text (the common
    # case, since every _*_document() helper puts the name/title
    # first) so the snippet adds new information instead of repeating
    # the label back.
    remainder = text
    if text.lower().startswith(label.lower()):
        remainder = text[len(label):].strip()

    if not remainder:
        return ""

    if len(remainder) <= SNIPPET_MAX_LENGTH:
        return remainder

    return remainder[:SNIPPET_MAX_LENGTH].rsplit(" ", 1)[0] + "..."


@router.get("", response_model=SearchResponse)
def search(
    q: str = Query(default="", description="Search text"),
    limit: int = Query(default=20, ge=1, le=50),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):

    if not q.strip():
        return SearchResponse(results=[])

    ranked = semantic_search(db, current_user.organization_id, q, top_k=limit)

    results = []

    for result in ranked:
        subtitle, url = describe_document(result.document)

        results.append(SearchResultItem(
            type=result.document.doc_type,
            id=result.document.id,
            label=result.document.label,
            subtitle=subtitle,
            snippet=_snippet(result.document.text, result.document.label),
            url=url,
            score=result.score,
        ))

    log_query_event(
        db,
        organization_id=current_user.organization_id,
        source="search",
        query_text=q,
        matched=len(results) > 0,
        actor_user_id=current_user.id,
        actor_email=current_user.email,
        result_count=len(results),
    )

    return SearchResponse(results=results)
