from pydantic import BaseModel


class MentionItem(BaseModel):

    type: str  # dataset | column | glossary_term | process | risk | control | discussion_thread
    id: str
    label: str
    subtitle: str


class MentionResponse(BaseModel):

    results: list[MentionItem]
