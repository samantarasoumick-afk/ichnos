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

from app.services.catalog_search_service import semantic_search


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


def _subtitle_and_url(document) -> tuple[str, str]:

    ref = document.ref

    if document.doc_type == "dataset":
        return ref.schema_name, f"/datasets/{document.id}"

    if document.doc_type == "glossary_term":
        subtitle = "Glossary term"
        if ref.domain:
            subtitle += f" · {ref.domain}"
        return subtitle, "/glossary"

    if document.doc_type == "process":
        subtitle = "Process"
        if ref.owner:
            subtitle += f" · {ref.owner}"
        return subtitle, "/processes"

    if document.doc_type == "risk":
        return f"Risk · {ref.category} · {ref.status}", "/risks"

    if document.doc_type == "control":
        return f"Control · {ref.control_type} · {ref.status}", "/risks"

    if document.doc_type == "discussion_thread":
        return f"{ref.thread_type.title()} · {ref.status}", f"/discussions/{document.id}"

    # Shouldn't happen - every doc_type build_corpus() can produce is
    # handled above - but fail soft with a link to nowhere useful
    # rather than a 500 if a new doc_type is ever added here without
    # updating this function.
    return document.doc_type, "/"


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
        subtitle, url = _subtitle_and_url(result.document)

        results.append(SearchResultItem(
            type=result.document.doc_type,
            id=result.document.id,
            label=result.document.label,
            subtitle=subtitle,
            snippet=_snippet(result.document.text, result.document.label),
            url=url,
            score=result.score,
        ))

    return SearchResponse(results=results)
