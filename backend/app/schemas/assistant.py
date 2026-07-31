from pydantic import BaseModel


class AskConversationTurn(BaseModel):
    """One prior turn in the conversation, as the frontend already tracks
    it client-side. Sent back on each request so follow-up questions
    ("what about its downstream tables?") have something to resolve
    against - previously this history was tracked in the UI but never
    forwarded to the backend, so genuine multi-turn follow-ups had no
    way to work even in principle.
    """

    role: str  # "user" | "assistant"
    text: str


class AskRequest(BaseModel):

    query: str
    history: list[AskConversationTurn] = []


class AskSource(BaseModel):

    type: str
    id: str
    label: str


class AskFollowUpSuggestion(BaseModel):
    """
    A clickable next question, generated from whatever the current
    answer's primary dataset is actually connected to (glossary terms,
    business process, contract, risks/controls, lineage) - so a
    conversation can walk the connected graph one hop at a time
    ("asked about the dataset, here's its process/contract/risk
    angle") instead of the person having to already know what else is
    worth asking.
    """

    label: str
    query: str


class AskResponse(BaseModel):

    answer: str
    sources: list[AskSource]
    follow_up_suggestions: list[AskFollowUpSuggestion] = []
