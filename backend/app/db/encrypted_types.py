import json

from sqlalchemy.types import TypeDecorator
from sqlalchemy.types import Text

from app.utils.crypto import encrypt_text
from app.utils.crypto import decrypt_text


class EncryptedJSON(TypeDecorator):
    """
    Stores a Python dict as an encrypted string in the database.
    Transparent to callers: reading/writing the column still works
    with plain dicts, but the bytes on disk (and in backups, and in
    a DB dump) are ciphertext, not readable JSON credentials.
    """

    impl = Text

    cache_ok = True

    def process_bind_param(self, value, dialect):

        if value is None:
            return None

        return encrypt_text(json.dumps(value))

    def process_result_value(self, value, dialect):

        if value is None:
            return None

        return json.loads(decrypt_text(value))
