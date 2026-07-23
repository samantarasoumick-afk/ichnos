import os

from datetime import datetime
from datetime import timedelta

from jose import jwt
from jose import JWTError
from jose import ExpiredSignatureError

SECRET_KEY = os.getenv("SECRET_KEY")

if not SECRET_KEY:
    raise RuntimeError(
        "SECRET_KEY is not set. Set it in the environment before "
        "starting the app - do not rely on a hardcoded default for "
        "signing auth tokens."
    )

ALGORITHM = "HS256"

ACCESS_TOKEN_EXPIRE_MINUTES = int(
    os.getenv(
        "ACCESS_TOKEN_EXPIRE_MINUTES",
        "60"
    )
)


def create_access_token(data: dict):

    to_encode = data.copy()

    expire = (
        datetime.utcnow()
        + timedelta(
            minutes=ACCESS_TOKEN_EXPIRE_MINUTES
        )
    )

    to_encode.update({
        "exp": expire
    })

    encoded_jwt = jwt.encode(
        to_encode,
        SECRET_KEY,
        algorithm=ALGORITHM
    )

    return encoded_jwt


def decode_access_token(token: str) -> dict:
    """
    Decode and verify a JWT. Raises jose.JWTError (or the more
    specific ExpiredSignatureError) if the signature is invalid,
    the token is malformed, or it has expired. Callers should treat
    any exception from this function as "not authenticated".
    """

    try:
        payload = jwt.decode(
            token,
            SECRET_KEY,
            algorithms=[ALGORITHM]
        )

    except ExpiredSignatureError:
        raise

    except JWTError:
        raise

    return payload
