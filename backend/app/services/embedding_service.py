"""
Dense-vector semantic search over the catalog - upgrades
catalog_search_service's TF-IDF retrieval with real embeddings (Voyage
AI, Anthropic's recommended embeddings partner, since Anthropic itself
doesn't offer an embeddings endpoint) whenever VOYAGE_API_KEY is
configured and reachable.

semantic_search() below is a drop-in replacement for
catalog_search_service.semantic_search(): identical signature, same
CorpusDocument/SearchResult return shape, same seven-doc-type corpus
(build_corpus() is reused as-is, unchanged). Every existing caller
(assistant_service.py's Ask retrieval, api/search.py's global search
bar) just imports semantic_search from here instead - nothing else
about how they consume results needs to change.

Falls back to the TF-IDF implementation, unchanged, whenever dense
embeddings aren't available: no VOYAGE_API_KEY set, a network/timeout
error, a malformed response, or an empty query/corpus. This mirrors
exactly how assistant_service.py's LLM path degrades to its own
deterministic paths when ANTHROPIC_API_KEY is unset or the call
fails - a missing/failing external dependency degrades the search
experience back to what it already was, it never breaks it. Existing
tests (none of which set VOYAGE_API_KEY) exercise this fallback path
by default, so TF-IDF behavior is unchanged unless the key is set.

Embeddings are computed once per entity and cached in
EntityEmbedding, keyed by a hash of the exact text that was embedded
plus the model name - an edit to a dataset's description or a switch
of VOYAGE_MODEL both naturally invalidate the cached vector on the
next search, no explicit re-indexing step required.
"""

import hashlib
import json
import os

import numpy as np
import requests

from sqlalchemy.orm import Session

from app.models.entity_embedding import EntityEmbedding
from app.services.catalog_search_service import CorpusDocument
from app.services.catalog_search_service import DocType
from app.services.catalog_search_service import SearchResult
from app.services.catalog_search_service import build_corpus
from app.services.catalog_search_service import semantic_search as tfidf_semantic_search


VOYAGE_EMBEDDINGS_URL = "https://api.voyageai.com/v1/embeddings"

# voyage-4-lite: Voyage's current cost/latency-optimized model (1024
# dims by default, up to 1M tokens per batch call) - the right default
# for embedding short catalog metadata rather than long documents.
# Overridable via VOYAGE_MODEL for anyone who wants voyage-4/-4-large's
# higher retrieval quality instead.
DEFAULT_VOYAGE_MODEL = "voyage-4-lite"

# Voyage allows up to 1,000 texts per call; batched well under that so
# even a large single-organization corpus never risks the per-call
# token ceiling, and a failure partway through only wastes one small
# batch's worth of calls rather than the whole corpus.
EMBED_BATCH_SIZE = 128


class EmbeddingUnavailableError(Exception):
    """Raised internally when Voyage can't be reached mid-batch - callers
    catch this (or any other exception) and fall back to TF-IDF rather
    than let it propagate."""


def _text_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _voyage_api_key() -> str | None:
    return os.getenv("VOYAGE_API_KEY") or None


def _voyage_model() -> str:
    return os.getenv("VOYAGE_MODEL", DEFAULT_VOYAGE_MODEL)


def _call_voyage_embeddings(texts: list[str], input_type: str) -> list[list[float]] | None:
    """
    Raw HTTP call to Voyage's embeddings endpoint - uses the `requests`
    dependency already in this project rather than adding the
    `voyageai` SDK, the same minimal-dependency convention
    assistant_service.py's _call_anthropic_api follows. Never raises:
    any failure (missing key, network, timeout, non-200, unexpected
    shape) returns None so the caller can fall back to TF-IDF.
    """

    api_key = _voyage_api_key()

    if not api_key or not texts:
        return None

    try:
        response = requests.post(
            VOYAGE_EMBEDDINGS_URL,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "input": texts,
                "model": _voyage_model(),
                "input_type": input_type,
            },
            timeout=15,
        )
        response.raise_for_status()

        body = response.json()
        # Voyage doesn't guarantee response ordering matches request
        # ordering - each item carries its own `index` back, so sort
        # on that rather than assume position.
        ordered = sorted(body["data"], key=lambda item: item["index"])
        embeddings = [item["embedding"] for item in ordered]

        if len(embeddings) != len(texts):
            return None

        return embeddings

    except Exception:
        return None


def _load_cached(db: Session, entity_type: str, entity_id: str) -> EntityEmbedding | None:
    return (
        db.query(EntityEmbedding)
        .filter(
            EntityEmbedding.entity_type == entity_type,
            EntityEmbedding.entity_id == entity_id,
        )
        .first()
    )


def get_or_create_embeddings(
    db: Session, documents: list[CorpusDocument]
) -> dict[tuple[str, str], list[float]]:
    """
    Returns {(doc_type, id): vector} for every document passed in,
    reusing a cached EntityEmbedding row when its text_hash and model
    both still match, and computing + persisting fresh vectors in
    batches for everything else. Commits after each successful batch
    (rather than once at the end) so a failure partway through a large
    corpus still keeps whatever was already embedded, instead of
    discarding real, paid-for API results.

    Raises EmbeddingUnavailableError if any batch that needed
    computing fails to come back - callers should catch this and fall
    back to TF-IDF for that request rather than rank a corpus with
    silent holes in it as "not similar to anything."
    """

    model = _voyage_model()
    vectors: dict[tuple[str, str], list[float]] = {}
    to_embed: list[CorpusDocument] = []

    for doc in documents:
        key = (doc.doc_type, doc.id)
        text_hash = _text_hash(doc.text)

        cached = _load_cached(db, doc.doc_type, doc.id)
        if cached and cached.text_hash == text_hash and cached.model == model:
            vectors[key] = json.loads(cached.vector)
        else:
            to_embed.append(doc)

    for start in range(0, len(to_embed), EMBED_BATCH_SIZE):
        batch = to_embed[start:start + EMBED_BATCH_SIZE]

        embeddings = _call_voyage_embeddings([doc.text for doc in batch], input_type="document")

        if embeddings is None:
            raise EmbeddingUnavailableError(
                f"Voyage embeddings call failed for a batch of {len(batch)} document(s)"
            )

        for doc, vector in zip(batch, embeddings):
            key = (doc.doc_type, doc.id)
            vectors[key] = vector
            text_hash = _text_hash(doc.text)

            existing = _load_cached(db, doc.doc_type, doc.id)
            if existing:
                existing.text_hash = text_hash
                existing.model = model
                existing.dimension = len(vector)
                existing.vector = json.dumps(vector)
            else:
                db.add(EntityEmbedding(
                    organization_id=doc.ref.organization_id,
                    entity_type=doc.doc_type,
                    entity_id=doc.id,
                    text_hash=text_hash,
                    model=model,
                    dimension=len(vector),
                    vector=json.dumps(vector),
                ))

        db.commit()

    return vectors


def _cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    denom = float(np.linalg.norm(a) * np.linalg.norm(b))
    if denom == 0.0:
        return 0.0
    return float(np.dot(a, b) / denom)


def semantic_search(
    db: Session,
    organization_id: str,
    query: str,
    top_k: int = 5,
    doc_types: tuple[DocType, ...] | None = None,
) -> list[SearchResult]:
    """
    Drop-in replacement for catalog_search_service.semantic_search():
    same signature, same return shape. Real dense-vector cosine
    similarity when VOYAGE_API_KEY is set and reachable; the exact
    same TF-IDF ranking as before in every other case, including any
    failure encountered along the way.
    """

    if not _voyage_api_key() or not query.strip():
        return tfidf_semantic_search(db, organization_id, query, top_k=top_k, doc_types=doc_types)

    corpus = build_corpus(db, organization_id, doc_types=doc_types)
    non_empty = [doc for doc in corpus if doc.text.strip()]

    if not non_empty:
        return []

    try:
        doc_vectors = get_or_create_embeddings(db, non_empty)

        query_embedding = _call_voyage_embeddings([query], input_type="query")
        if query_embedding is None:
            raise EmbeddingUnavailableError("Voyage embeddings call failed for the query text")

        query_vector = np.array(query_embedding[0])

        scored: list[tuple[CorpusDocument, float]] = []
        for doc in non_empty:
            key = (doc.doc_type, doc.id)
            if key not in doc_vectors:
                continue
            score = _cosine_similarity(query_vector, np.array(doc_vectors[key]))
            scored.append((doc, score))

        scored.sort(key=lambda pair: pair[1], reverse=True)

        return [
            SearchResult(document=doc, score=score)
            for doc, score in scored[:top_k]
            if score > 0
        ]

    except Exception:
        # Whatever embeddings were successfully computed above are
        # already committed (get_or_create_embeddings commits per
        # batch) - nothing to roll back, just serve this request from
        # TF-IDF instead.
        return tfidf_semantic_search(db, organization_id, query, top_k=top_k, doc_types=doc_types)
