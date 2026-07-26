"""
Local, free semantic-ish search over the catalog: TF-IDF vectorization
+ cosine similarity via scikit-learn - no external API, no model
download, no per-query cost. Not "real" embeddings in the neural-net
sense, but it captures term overlap and relevance well enough at
catalog scale to be a genuine improvement over exact substring
matching. Two callers: the NL Q&A assistant
(app/services/assistant_service.py) falls back to this when no more
specific intent applies, and app/api/search.py exposes it directly as
the app's global, cross-entity search bar.

Covers every entity type a user might plausibly be looking for by
name/description rather than just datasets + glossary terms:
BusinessProcess, Risk, Control, and GovernanceThread (discussions) are
all included in the corpus too. DataSource (connections) and User
(team members) are deliberately left out - searching for "the
Postgres connection" or "the person named Priya" isn't really what
this bar is for, and the assistant never needed them either.

Computed fresh per request rather than cached/indexed - a few
thousand rows across all these tables fit comfortably in that budget.
Revisit with a real cache or persisted index if that assumption stops
holding.
"""

from dataclasses import dataclass
from typing import Literal

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from sqlalchemy.orm import Session

from app.models.business_process import BusinessProcess
from app.models.control import Control
from app.models.dataset import Dataset
from app.models.governance import BusinessGlossaryTerm
from app.models.governance_thread import GovernanceThread
from app.models.risk import Risk


DocType = Literal[
    "dataset",
    "glossary_term",
    "process",
    "risk",
    "control",
    "discussion_thread",
]


@dataclass
class CorpusDocument:

    doc_type: DocType
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


def _process_document(process: BusinessProcess) -> CorpusDocument:

    text_parts = [process.name, process.description, process.narrative, process.owner]

    return CorpusDocument(
        doc_type="process",
        id=process.id,
        label=process.name,
        text=" ".join(part for part in text_parts if part),
        ref=process,
    )


def _risk_document(risk: Risk) -> CorpusDocument:

    text_parts = [risk.title, risk.description, risk.category, risk.status]

    return CorpusDocument(
        doc_type="risk",
        id=risk.id,
        label=risk.title,
        text=" ".join(part for part in text_parts if part),
        ref=risk,
    )


def _control_document(control: Control) -> CorpusDocument:

    text_parts = [control.name, control.description, control.control_type, control.status]

    return CorpusDocument(
        doc_type="control",
        id=control.id,
        label=control.name,
        text=" ".join(part for part in text_parts if part),
        ref=control,
    )


def _thread_document(thread: GovernanceThread) -> CorpusDocument:

    text_parts = [thread.title, thread.body, thread.thread_type]

    return CorpusDocument(
        doc_type="discussion_thread",
        id=thread.id,
        label=thread.title,
        text=" ".join(part for part in text_parts if part),
        ref=thread,
    )


def build_corpus(
    db: Session,
    organization_id: str,
    doc_types: tuple[DocType, ...] | None = None,
) -> list[CorpusDocument]:
    """
    doc_types restricts which tables get queried at all (not just a
    post-hoc filter) - e.g. the NL Q&A assistant only ever wants
    dataset/glossary_term documents, since its detail-card and
    fallback-snippet builders are written against those two shapes
    specifically. Pass None (the default, used by the global search
    bar in app/api/search.py) to search every entity type.
    """

    def wants(doc_type: DocType) -> bool:
        return doc_types is None or doc_type in doc_types

    documents: list[CorpusDocument] = []

    if wants("dataset"):
        datasets = (
            db.query(Dataset)
            .filter(Dataset.organization_id == organization_id)
            .all()
        )
        documents += [_dataset_document(d) for d in datasets]

    if wants("glossary_term"):
        terms = (
            db.query(BusinessGlossaryTerm)
            .filter(BusinessGlossaryTerm.organization_id == organization_id)
            .all()
        )
        documents += [_glossary_document(t) for t in terms]

    if wants("process"):
        processes = (
            db.query(BusinessProcess)
            .filter(BusinessProcess.organization_id == organization_id)
            .all()
        )
        documents += [_process_document(p) for p in processes]

    if wants("risk"):
        risks = (
            db.query(Risk)
            .filter(Risk.organization_id == organization_id)
            .all()
        )
        documents += [_risk_document(r) for r in risks]

    if wants("control"):
        controls = (
            db.query(Control)
            .filter(Control.organization_id == organization_id)
            .all()
        )
        documents += [_control_document(c) for c in controls]

    if wants("discussion_thread"):
        threads = (
            db.query(GovernanceThread)
            .filter(GovernanceThread.organization_id == organization_id)
            .all()
        )
        documents += [_thread_document(t) for t in threads]

    return documents


def semantic_search(
    db: Session,
    organization_id: str,
    query: str,
    top_k: int = 5,
    doc_types: tuple[DocType, ...] | None = None,
) -> list[SearchResult]:

    corpus = build_corpus(db, organization_id, doc_types=doc_types)

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
