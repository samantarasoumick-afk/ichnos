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


class AskResponse(BaseModel):

    answer: str
    sources: list[AskSource]
