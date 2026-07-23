import re
import uuid

from datetime import datetime, timedelta

from fastapi import APIRouter
from fastapi import Depends
from fastapi import HTTPException

from sqlalchemy.orm import Session

from app.db.session import get_db

from app.models.audit_log import AuditLog
from app.models.user import User
from app.models.organization import Organization

from app.schemas.user import UserCreate
from app.schemas.user import UserLogin

from app.auth.security import hash_password
from app.auth.security import verify_password

from app.auth.jwt_handler import create_access_token

from app.auth.dependencies import get_current_user

from app.services.audit_service import log_audit_event


router = APIRouter(
    prefix="/api/auth",
    tags=["auth"]
)

# Brute-force protection on login: after this many failed attempts
# for a given account within the window, further attempts are
# rejected outright (without even checking the password) until the
# oldest failed attempt ages out of the window. Backed by the
# existing audit_logs table rather than a new table or an in-memory
# counter, so it survives restarts and shows up on the Audit Log page
# as a side benefit.
LOGIN_LOCKOUT_THRESHOLD = 5
LOGIN_LOCKOUT_WINDOW_MINUTES = 15


def _recent_failed_login_count(db: Session, user_id: str) -> int:

    cutoff = datetime.utcnow() - timedelta(minutes=LOGIN_LOCKOUT_WINDOW_MINUTES)

    return (
        db.query(AuditLog)
        .filter(
            AuditLog.actor_user_id == user_id,
            AuditLog.action == "user.login_failed",
            AuditLog.created_at >= cutoff,
        )
        .count()
    )


def _slugify(name: str) -> str:

    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")

    return slug or uuid.uuid4().hex[:8]


def _unique_slug(db: Session, base_slug: str) -> str:

    slug = base_slug
    suffix = 1

    while db.query(Organization).filter(Organization.slug == slug).first():
        suffix += 1
        slug = f"{base_slug}-{suffix}"

    return slug


@router.post("/register")
def register_user(
    user: UserCreate,
    db: Session = Depends(get_db)
):

    existing_user = (
        db.query(User)
        .filter(User.email == user.email)
        .first()
    )

    if existing_user:

        raise HTTPException(
            status_code=400,
            detail="User already exists"
        )

    organization = Organization(
        name=user.organization_name,
        slug=_unique_slug(db, _slugify(user.organization_name))
    )

    db.add(organization)
    db.flush()

    # First user in a brand-new organization is its admin.
    new_user = User(
        email=user.email,
        password_hash=hash_password(user.password),
        role="admin",
        organization_id=organization.id
    )

    db.add(new_user)
    db.flush()

    log_audit_event(
        db,
        organization_id=organization.id,
        action="user.register",
        actor_user_id=new_user.id,
        actor_email=new_user.email,
        resource_type="organization",
        resource_id=organization.id,
        details=f"Registered as admin of new organization '{organization.name}'",
    )

    db.commit()

    return {
        "message": "User registered successfully",
        "organization_id": organization.id,
        "organization_slug": organization.slug
    }


@router.post("/login")
def login_user(
    user: UserLogin,
    db: Session = Depends(get_db)
):

    existing_user = (
        db.query(User)
        .filter(User.email == user.email)
        .first()
    )

    if not existing_user:

        raise HTTPException(
            status_code=401,
            detail="Invalid credentials"
        )

    if _recent_failed_login_count(db, existing_user.id) >= LOGIN_LOCKOUT_THRESHOLD:

        raise HTTPException(
            status_code=429,
            detail=(
                "Too many failed login attempts. Please try again in "
                f"{LOGIN_LOCKOUT_WINDOW_MINUTES} minutes."
            )
        )

    valid_password = verify_password(
        user.password,
        existing_user.password_hash
    )

    if not valid_password:

        log_audit_event(
            db,
            organization_id=existing_user.organization_id,
            action="user.login_failed",
            actor_user_id=existing_user.id,
            actor_email=existing_user.email,
            details="Incorrect password",
        )
        db.commit()

        raise HTTPException(
            status_code=401,
            detail="Invalid credentials"
        )

    if not existing_user.is_active:

        raise HTTPException(
            status_code=401,
            detail="This account has been deactivated"
        )

    token = create_access_token({
        "sub": existing_user.email
    })

    log_audit_event(
        db,
        organization_id=existing_user.organization_id,
        action="user.login",
        actor_user_id=existing_user.id,
        actor_email=existing_user.email,
    )
    db.commit()

    return {
        "access_token": token,
        "token_type": "bearer"
    }


@router.get("/me")
def get_me(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):

    organization = (
        db.query(Organization)
        .filter(Organization.id == current_user.organization_id)
        .first()
    )

    return {
        "id": current_user.id,
        "email": current_user.email,
        "role": current_user.role,
        "organization_id": current_user.organization_id,
        "organization_name": organization.name if organization else None,
        "organization_slug": organization.slug if organization else None,
    }
