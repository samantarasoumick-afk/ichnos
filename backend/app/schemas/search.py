from pydantic import BaseModel


class SearchResultItem(BaseModel):

    type: str  # source | dataset | column | glossary_term | process | risk | control | discussion_thread
    id: str
    label: str

    # A short, type-specific line under the label - e.g. a dataset's
    # schema, a risk's status, a thread's type - so the dropdown reads
    # as more than just a bare name.
    subtitle: str

    # A short excerpt of the matched text, for a little context beyond
    # the label alone. Empty string if there's nothing beyond the
    # label itself worth showing.
    snippet: str

    # Where clicking this result should navigate. Datasets and
    # discussion threads have their own detail pages; everything else
    # links to its list page (no deep-linking/highlight support there
    # yet - see task #207/#208 for follow-up work in this area).
    url: str

    score: float


class SearchResponse(BaseModel):

    results: list[SearchResultItem]
