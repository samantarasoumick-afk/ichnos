from fastapi import Depends
from fastapi import HTTPException
from fastapi import status

from fastapi.security import OAuth2PasswordBearer

from jose import JWTError

from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.user import User
from app.auth.jwt_handler import decode_access_token


# tokenUrl is just used to point interactive API docs at the login
# route - the dependency itself accepts any bearer token in the
# Authorization header.
oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl="/api/auth/login",
    auto_error=False
)


def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
) -> User:

    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"}
    )

    if not token:
        raise credentials_exception

    try:
        payload = decode_access_token(token)

    except JWTError:
        raise credentials_exception

    email = payload.get("sub")

    if not email:
        raise credentials_exception

    # Role/org are re-read from the DB on every request rather than
    # trusted from the token payload, so a role change or org move
    # takes effect immediately instead of only after the token expires.
    user = (
        db.query(User)
        .filter(User.email == email)
        .first()
    )

    if not user:
        raise credentials_exception

    if not user.is_active:
        raise credentials_exception

    return user


def require_role(*allowed_roles: str):
    """
    Dependency factory: require_role("admin", "steward") gates a
    route to only those roles, returning 403 for anyone else
    (including authenticated users with a different role).
    """

    def dependency(
        current_user: User = Depends(get_current_user)
    ) -> User:

        if current_user.role not in allowed_roles:

            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    "This action requires one of the following "
                    f"roles: {', '.join(allowed_roles)}"
                )
            )

        return current_user

    return dependency
