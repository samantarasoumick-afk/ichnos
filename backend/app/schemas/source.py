from pydantic import BaseModel


class SourceCreate(BaseModel):

    name: str

    type: str

    connection_config: dict