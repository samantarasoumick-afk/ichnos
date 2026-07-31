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
BusinessProcess, Risk, Control, GovernanceThread (discussions),
individual DatasetColumns, and DataSource (connections/systems) are
all included in the corpus too. User (team members) is the one thing
deliberately left out - "the person named Priya" isn't what this bar
is for.

Source, dataset, and column are treated as the three primary tiers a
catalog search should surface (app/api/search.py reserves a slice of
its result budget for each of them specifically) - so searching for a
system name like "Salesforce" returns the source itself, which can
then be drilled into its datasets, which can be drilled into their
columns, rather than a system-level question only ever surfacing
whichever individual table happens to rank highest.

Column documents deliberately never index DatasetColumn.sample_values
- that field can hold real (unmasked) example values for PII/sensitive
columns, and a search snippet is not a context where that data's
existing masking/role restrictions get enforced. Name, description,
and classification are searchable; actual data values are not.

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
from app.models.column import DatasetColumn
from app.models.control import Control
from app.models.dataset import Dataset
from app.models.governance import BusinessGlossaryTerm
from app.models.governance_thread import GovernanceThread
from app.models.risk import Risk
from app.models.source import DataSource

from app.services.ecosystem_service import compute_source_rollup


DocType = Literal[
    "source",
    "dataset",
    "column",
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


def _source_document(source: DataSource, source_datasets: list[Dataset]) -> CorpusDocument:
    """
    Unlike every other doc_type, `ref` here is not the bare ORM object -
    describe_document() needs the dataset-count/column-count/PII/worst-
    governance rollup too, and DataSource has no ORM-level relationship
    to its datasets to recompute that lazily later without another
    query. Bundled once, here, where the full per-source dataset list
    is already on hand from build_corpus().
    """

    rollup = compute_source_rollup(source_datasets)

    dataset_labels = " ".join(f"{d.schema_name}.{d.name} {d.name}" for d in source_datasets)
    text_parts = [source.name, source.type, dataset_labels]

    return CorpusDocument(
        doc_type="source",
        id=source.id,
        label=source.name,
        text=" ".join(part for part in text_parts if part),
        ref={"source": source, **rollup},
    )


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


def _column_document(column: DatasetColumn) -> CorpusDocument:

    dataset = column.dataset

    text_parts = [
        column.name,
        dataset.name if dataset else None,
        dataset.schema_name if dataset else None,
        column.description,
        column.classification,
        column.dpdp_category,
        column.data_type,
    ]

    return CorpusDocument(
        doc_type="column",
        id=column.id,
        label=column.name,
        text=" ".join(part for part in text_parts if part),
        ref=column,
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

    if wants("source"):
        sources = (
            db.query(DataSource)
            .filter(DataSource.organization_id == organization_id)
            .all()
        )
        # Needed for the rollup even if "dataset" itself wasn't
        # requested in this call - the two are queried independently
        # rather than sharing the block below, since doc_types can ask
        # for one without the other.
        source_datasets_all = (
            db.query(Dataset)
            .filter(Dataset.organization_id == organization_id)
            .all()
        )
        datasets_by_source: dict[str, list[Dataset]] = {}
        for d in source_datasets_all:
            datasets_by_source.setdefault(d.source_id, []).append(d)
        documents += [
            _source_document(s, datasets_by_source.get(s.id, []))
            for s in sources
        ]

    if wants("dataset"):
        datasets = (
            db.query(Dataset)
            .filter(Dataset.organization_id == organization_id)
            .all()
        )
        documents += [_dataset_document(d) for d in datasets]

    if wants("column"):
        columns = (
            db.query(DatasetColumn)
            .join(Dataset, DatasetColumn.dataset_id == Dataset.id)
            .filter(Dataset.organization_id == organization_id)
            .all()
        )
        documents += [_column_document(c) for c in columns]

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


SNIPPET_MAX_LENGTH = 160


def build_result_snippet(text: str, label: str) -> str:
    """
    Shared by app/api/search.py and assistant_service.py's semantic-
    search fallback so a result reads identically - same trimming, same
    max length - regardless of which surface (the search bar or Ask'Fe')
    happened to render it. The label itself is already shown prominently
    wherever this is used, so strip it out of the snippet if it's a
    prefix of the corpus text (the common case, since every
    _*_document() helper puts the name/title first) - that way the
    snippet adds new information instead of repeating the label back.
    """

    remainder = text
    if text.lower().startswith(label.lower()):
        remainder = text[len(label):].strip()

    if not remainder:
        return ""

    if len(remainder) <= SNIPPET_MAX_LENGTH:
        return remainder

    return remainder[:SNIPPET_MAX_LENGTH].rsplit(" ", 1)[0] + "..."


def describe_document(document: CorpusDocument) -> tuple[str, str]:
    """
    A short type-specific subtitle plus the frontend route a result
    should link to - shared by the global search bar
    (app/api/search.py) and the "@" mention picker (app/api/mentions.py)
    so the two don't drift on how a given entity type is labeled or
    routed to.
    """

    ref = document.ref

    if document.doc_type == "source":
        # ref is the {"source": ..., **rollup} dict built in
        # _source_document() above, not a bare ORM object - see that
        # function's docstring for why.
        source = ref["source"]
        bits = [f"{ref['dataset_count']} dataset{'s' if ref['dataset_count'] != 1 else ''}"]
        if ref["total_columns"]:
            bits.append(f"{ref['total_columns']} columns")
        if ref["pii_columns"]:
            bits.append(f"{ref['pii_columns']} PII")
        subtitle = f"Source · {source.type} · " + ", ".join(bits)
        return subtitle, f"/ecosystem?sourceId={document.id}"

    if document.doc_type == "dataset":
        return ref.schema_name, f"/datasets/{document.id}"

    if document.doc_type == "column":
        dataset = ref.dataset
        label = f"{dataset.schema_name}.{dataset.name}" if dataset else "Unknown dataset"
        subtitle = f"Column · {label}"
        if ref.classification and ref.classification.upper() not in ("NONE", ""):
            subtitle += f" · {ref.classification}"
        url = f"/datasets/{dataset.id}?tab=columns&highlightColumn={document.id}" if dataset else "/"
        return subtitle, url

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


def list_mentionable(
    db: Session,
    organization_id: str,
    query: str = "",
    limit: int = 8,
) -> list[CorpusDocument]:
    """
    Powers the "@" mention picker in Ask and the global search bar -
    a different job from semantic_search() above. That's relevance
    ranking over free-form question/search text via TF-IDF, which
    needs whole, complete words to find term overlap with. This is
    name-prefix autocomplete: someone has typed "@cust" and expects
    "customers" to show up immediately, which TF-IDF can't do (a
    partial token like "cust" shares no vocabulary with the indexed
    word "customers"). Plain case-insensitive substring matching on
    the label instead, with results starting with the query ranked
    above results merely containing it, then alphabetically.

    An empty query (just typed "@" with nothing after it yet) returns
    the first `limit` documents alphabetically by label, across all
    types, as a reasonable starting list rather than nothing at all.
    """

    corpus = build_corpus(db, organization_id)

    normalized_query = query.strip().lower()

    if not normalized_query:
        ranked = sorted(corpus, key=lambda doc: doc.label.lower())
        return ranked[:limit]

    matches = [doc for doc in corpus if normalized_query in doc.label.lower()]

    matches.sort(
        key=lambda doc: (
            not doc.label.lower().startswith(normalized_query),
            doc.label.lower(),
        )
    )

    return matches[:limit]
