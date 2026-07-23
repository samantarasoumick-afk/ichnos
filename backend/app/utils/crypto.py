"""
Symmetric encryption helper used to protect secrets at rest
(e.g. DataSource.connection_config, which holds DB credentials).

ENCRYPTION_KEY must be a urlsafe-base64-encoded 32-byte key
(the format Fernet.generate_key() produces). Generate one with:

    python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

and set it as the ENCRYPTION_KEY environment variable in every
environment that reads or writes encrypted columns. Rotating this
key without a re-encryption migration will make existing encrypted
rows unreadable.
"""

import os

from cryptography.fernet import Fernet
from cryptography.fernet import InvalidToken


_ENV_VAR = "ENCRYPTION_KEY"


def _get_fernet() -> Fernet:

    key = os.getenv(_ENV_VAR)

    if not key:
        raise RuntimeError(
            f"{_ENV_VAR} is not set. Generate one with "
            "`python -c \"from cryptography.fernet import Fernet; "
            "print(Fernet.generate_key().decode())\"` and set it "
            "in the environment before starting the app."
        )

    return Fernet(key.encode())


def encrypt_text(plaintext: str) -> str:

    return _get_fernet().encrypt(
        plaintext.encode()
    ).decode()


def decrypt_text(ciphertext: str) -> str:

    try:
        return _get_fernet().decrypt(
            ciphertext.encode()
        ).decode()

    except InvalidToken as exc:
        raise ValueError(
            "Could not decrypt value - wrong ENCRYPTION_KEY or corrupted data."
        ) from exc
