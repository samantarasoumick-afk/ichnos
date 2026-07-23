"""
Local, free semantic-ish search over the catalog: TF-IDF vectorization
+ cosine similarity via scikit-learn - no external API, no model
download, no per-query cost. Not "real" embeddings in the neural-net
sense, but it captures term overlap and relevance well enough at
catalog scale to be a genuine improvement over exact substring
matching, and it's the retrieval layer the NL Q&A assistant
(app/services/assistant_service.py) falls back to when no more
specific answer applies.

Computed fresh per request rather than cached/indexed - a few
thousand datasets and glossary terms fit comfortably in that budget.
Revisit with a real cache or persisted index if that assumption stops
holding.
"""

from dataclasses import dataclass
from typing import Literal

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from sqlalchemy.orm import Session

from app.models.dataset import Dataset
from app.models.governance import BusinessGlossaryTerm


@dataclass
class CorpusDocument:

    doc_type: Literal["dataset", "glossary_term"]
    id: str
    label: str
    text: str
    ref: object  # the underlying ORM object - callers use this for rich detail


@dataclass
class SearchResult:

    document: CorpusDocument
    score: float


def _dataset_document(dataset: Dataset) -> CorpusDocument:

    column_names = " ".join(column.name or "" for column in dataset.columns)

    text_parts = [
        dataset.name,
        dataset.schema_name,
        dataset.description,
        dataset.ai_summary,
        dataset.domain,
        dataset.tags,
        dataset.owner,
        dataset.steward,
        column_names,
    ]

    return CorpusDocument(
        doc_type="dataset",
        id=dataset.id,
        label=f"{dataset.schema_name}.{dataset.name}",
        text=" ".join(part for part in text_parts if part),
        ref=dataset,
    )


def _glossary_document(term: BusinessGlossaryTerm) -> CorpusDocument:

    text_parts = [term.term, term.definition, term.domain, term.owner]

    return CorpusDocument(
        doc_type="glossary_term",
        id=term.id,
        label=term.term,
        text=" ".join(part for part in text_parts if part),
        ref=term,
    )


def build_corpus(db: Session, organization_id: str) -> list[CorpusDocument]:

    datasets = (
        db.query(Dataset)
        .filter(Dataset.organization_id == organization_id)
        .all()
    )

    terms = (
        db.query(BusinessGlossaryTerm)
        .filter(BusinessGlossaryTerm.organization_id == organization_id)
        .all()
    )

    documents = [_dataset_document(d) for d in datasets]
    documents += [_glossary_document(t) for t in terms]

    return documents


def semantic_search(
    db: Session,
    organization_id: str,
    query: str,
    top_k: int = 5,
) -> list[SearchResult]:

    corpus = build_corpus(db, organization_id)

    non_empty = [doc for doc in corpus if doc.text.strip()]

    if not non_empty or not query.strip():
        return []

    vectorizer = TfidfVectorizer(stop_words="english")

    try:
        matrix = vectorizer.fit_transform(
            [doc.text for doc in non_empty] + [query]
        )
    except ValueError:
        # Every document/query was pure stopwords or empty after
        # tokenization - nothing meaningful to compare against.
        return []

    doc_vectors = matrix[:-1]
    query_vector = matrix[-1]

    similarities = cosine_similarity(query_vector, doc_vectors)[0]

    ranked = sorted(
        zip(non_empty, similarities),
        key=lambda pair: pair[1],
        reverse=True,
    )

    return [
        SearchResult(document=doc, score=float(score))
        for doc, score in ranked[:top_k]
        if score > 0
    ]
