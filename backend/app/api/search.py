"""
The app's global, cross-entity search bar (top nav "Search everything"
box) - not to be confused with the Ask assistant, which answers
questions in prose. This just finds things and links to them. Both
sit on top of the same retrieval in app/services/embedding_service.py
(real Voyage embeddings when configured, TF-IDF fallback otherwise).
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

from app.services.catalog_search_service import build_result_snippet
from app.services.catalog_search_service import describe_document
from app.services.embedding_service import semantic_search
from app.services.query_log_service import log_query_event


router = APIRouter(
    prefix="/api/search",
    tags=["search"]
)

# The three tiers a catalog search should treat as first-class: a
# customer searching for a system name should get a source-level hit,
# not just whichever individual dataset/column happens to rank
# highest overall. A single flat top-K ranking across every entity
# type tends to get crowded out by whichever type is most numerous
# (columns, in most catalogs) - reserving a slice of the budget for
# each of these three guarantees representation from every level of
# the source -> dataset -> column hierarchy.
CORE_TYPES: tuple[str, ...] = ("source", "dataset", "column")


@router.get("", response_model=SearchResponse)
def search(
    q: str = Query(default="", description="Search text"),
    limit: int = Query(default=20, ge=1, le=50),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):

    if not q.strip():
        return SearchResponse(results=[])

    seen: set[tuple[str, str]] = set()
    ranked = []

    # Pass 1: reserve a fair minimum share of the overall limit for
    # each core tier, ranked independently within its own type so one
    # tier's matches can't crowd another's out.
    per_type_reserve = max(1, limit // len(CORE_TYPES))
    for doc_type in CORE_TYPES:
        for result in semantic_search(
            db, current_user.organization_id, q,
            top_k=per_type_reserve, doc_types=(doc_type,),
        ):
            key = (result.document.doc_type, result.document.id)
            if key in seen:
                continue
            seen.add(key)
            ranked.append(result)

    # Pass 2: fill whatever's left of the overall limit from a single
    # combined ranking across every type (core types already captured
    # above are skipped via `seen`) - this is what surfaces
    # glossary/process/risk/control/discussion hits, and lets a core
    # type get extra representation beyond its reserved minimum when
    # it genuinely dominates the results and there's room left.
    if len(ranked) < limit:
        for result in semantic_search(db, current_user.organization_id, q, top_k=limit * 2):
            if len(ranked) >= limit:
                break
            key = (result.document.doc_type, result.document.id)
            if key in seen:
                continue
            seen.add(key)
            ranked.append(result)

    ranked = ranked[:limit]

    results = []

    for result in ranked:
        subtitle, url = describe_document(result.document)

        results.append(SearchResultItem(
            type=result.document.doc_type,
            id=result.document.id,
            label=result.document.label,
            subtitle=subtitle,
            snippet=build_result_snippet(result.document.text, result.document.label),
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
