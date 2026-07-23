from pydantic import BaseModel


class AskRequest(BaseModel):

    query: str


class AskSource(BaseModel):

    type: str
    id: str
    label: str


class AskResponse(BaseModel):

    answer: str
    sources: list[AskSource]
