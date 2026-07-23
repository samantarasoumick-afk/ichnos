from pydantic import BaseModel


class TableauConnectRequest(BaseModel):

    name: str

    server_url: str

    # Empty string means the server's Default site.
    site_content_url: str = ""

    token_name: str

    token_value: str
