import hashlib
import os
import re
import secrets
import uuid

from datetime import datetime, timedelta

from fastapi import APIRouter
from fastapi import Depends
from fastapi import HTTPException
from fastapi import Request

from fastapi.responses import JSONResponse
from fastapi.responses import RedirectResponse

from sqlalchemy.orm import Session

from app.db.session import get_db

from app.models.audit_log import AuditLog
from app.models.magic_login_token import MagicLoginToken
from app.models.user import User
from app.models.organization import Organization

from app.schemas.user import GitHubOAuthCallback
from app.schemas.user import MagicLinkRequest
from app.schemas.user import MagicLinkVerify
from app.schemas.user import UserCreate
from app.schemas.user import UserLogin

from app.auth.security import hash_password
from app.auth.security import verify_password

from app.auth.jwt_handler import create_access_token

from app.auth.dependencies import get_current_user

from app.services import oauth_service
from app.services.audit_service import log_audit_event
from app.services.email_service import send_email


router = APIRouter(
    prefix="/api/auth",
    tags=["auth"]
)

# Where the frontend actually lives, for building the link in the
# magic-link email. Defaults to local dev; self-hosted setups should
# set this to the app's real public URL (e.g.
# https://app.datafe.yourdomain.com) once one exists - see
# docs/SELF_HOSTING.md.
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:3000").rstrip("/")

# Passwordless login: a short-lived, single-use link mailed to the
# account's own address. This doubles as the de facto password-reset
# path (there's no separate "reset my password" flow) - if you can
# receive mail at the account's address, you can always get back in.
MAGIC_LINK_EXPIRE_MINUTES = 15
MAGIC_LINK_REQUEST_LIMIT = 3
MAGIC_LINK_REQUEST_WINDOW_MINUTES = 15

MAGIC_LINK_GENERIC_RESPONSE = {
    "message": (
        "If an account exists for that email, we've sent a login link. "
        "It expires in 15 minutes."
    )
}


def _hash_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode()).hexdigest()

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

    # GitHub-only accounts (created via OAuth, never given a
    # password) have no hash to check against - fail the same way an
    # incorrect password would, rather than passing None into
    # verify_password().
    valid_password = (
        existing_user.password_hash is not None
        and verify_password(user.password, existing_user.password_hash)
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


@router.post("/magic-link/request")
def request_magic_link(
    payload: MagicLinkRequest,
    db: Session = Depends(get_db)
):
    """
    Always returns the same generic message regardless of whether the
    email matches an account, is inactive, or is being rate-limited -
    a different response for each case would let someone enumerate
    which emails have accounts just by requesting links for them.
    """

    existing_user = (
        db.query(User)
        .filter(User.email == payload.email)
        .first()
    )

    if not existing_user or not existing_user.is_active:
        return MAGIC_LINK_GENERIC_RESPONSE

    cutoff = datetime.utcnow() - timedelta(minutes=MAGIC_LINK_REQUEST_WINDOW_MINUTES)

    recent_requests = (
        db.query(AuditLog)
        .filter(
            AuditLog.actor_user_id == existing_user.id,
            AuditLog.action == "user.magic_link_requested",
            AuditLog.created_at >= cutoff,
        )
        .count()
    )

    if recent_requests >= MAGIC_LINK_REQUEST_LIMIT:
        return MAGIC_LINK_GENERIC_RESPONSE

    raw_token = secrets.token_urlsafe(32)

    db.add(
        MagicLoginToken(
            user_id=existing_user.id,
            token_hash=_hash_token(raw_token),
            expires_at=datetime.utcnow() + timedelta(minutes=MAGIC_LINK_EXPIRE_MINUTES),
        )
    )

    login_url = f"{FRONTEND_URL}/login/magic?token={raw_token}"

    send_email(
        to=existing_user.email,
        subject="Your DataFe login link",
        body=(
            "Click the link below to sign in to DataFe. It expires in "
            f"{MAGIC_LINK_EXPIRE_MINUTES} minutes and can only be used once.\n\n"
            f"{login_url}\n\n"
            "If you didn't request this, you can safely ignore this email - "
            "your account is unaffected."
        ),
    )

    log_audit_event(
        db,
        organization_id=existing_user.organization_id,
        action="user.magic_link_requested",
        actor_user_id=existing_user.id,
        actor_email=existing_user.email,
    )
    db.commit()

    return MAGIC_LINK_GENERIC_RESPONSE


@router.post("/magic-link/verify")
def verify_magic_link(
    payload: MagicLinkVerify,
    db: Session = Depends(get_db)
):

    token_hash = _hash_token(payload.token)

    token = (
        db.query(MagicLoginToken)
        .filter(MagicLoginToken.token_hash == token_hash)
        .first()
    )

    if not token or token.used_at is not None or token.expires_at < datetime.utcnow():
        raise HTTPException(
            status_code=400,
            detail="This login link is invalid or has expired. Request a new one."
        )

    user = db.query(User).filter(User.id == token.user_id).first()

    if not user or not user.is_active:
        raise HTTPException(
            status_code=400,
            detail="This login link is invalid or has expired. Request a new one."
        )

    token.used_at = datetime.utcnow()

    access_token = create_access_token({
        "sub": user.email
    })

    log_audit_event(
        db,
        organization_id=user.organization_id,
        action="user.magic_link_login",
        actor_user_id=user.id,
        actor_email=user.email,
    )
    db.commit()

    return {
        "access_token": access_token,
        "token_type": "bearer"
    }


GITHUB_OAUTH_STATE_COOKIE = "datafe_github_oauth_state"

# Plenty for a browser round trip to GitHub's consent screen and back
# - this only needs to outlive the redirect, not a user session.
GITHUB_OAUTH_STATE_MAX_AGE_SECONDS = 600


def _github_redirect_uri() -> str:
    # Must exactly match the "Authorization callback URL" configured
    # on the GitHub OAuth App (see docs/SELF_HOSTING.md) - GitHub
    # rejects the code exchange otherwise. Lands on a real Next.js
    # page (frontend/src/app/login/github/callback/page.tsx), not a
    # backend route, since it's a full browser navigation.
    return f"{FRONTEND_URL}/login/github/callback"


@router.get("/oauth/github/start")
def start_github_oauth():
    """
    Kicks off "Sign in with GitHub" by redirecting the browser to
    GitHub's consent screen. Not an XHR endpoint - the frontend links
    to this directly (a plain <a href>) so the browser does a real
    page navigation and GitHub's redirect back to
    FRONTEND_URL/login/github/callback lands as an ordinary page load,
    not a blocked cross-origin fetch.
    """

    state = secrets.token_urlsafe(24)

    try:
        authorize_url = oauth_service.build_authorize_url(
            redirect_uri=_github_redirect_uri(),
            state=state,
        )
    except oauth_service.GitHubOAuthError as exc:
        raise HTTPException(status_code=503, detail=str(exc))

    response = RedirectResponse(url=authorize_url)

    # Bound to this browser via a short-lived cookie rather than a DB
    # row - the callback below compares the `state` query param GitHub
    # sends back against this cookie (both must be present and match).
    # This is the standard "double-submit" CSRF check for OAuth state
    # when there's no server-side session/nonce table to persist it in.
    response.set_cookie(
        key=GITHUB_OAUTH_STATE_COOKIE,
        value=state,
        max_age=GITHUB_OAUTH_STATE_MAX_AGE_SECONDS,
        httponly=True,
        samesite="lax",
    )

    return response


@router.post("/oauth/github/callback")
def github_oauth_callback(
    payload: GitHubOAuthCallback,
    request: Request,
    db: Session = Depends(get_db)
):

    expected_state = request.cookies.get(GITHUB_OAUTH_STATE_COOKIE)

    if not expected_state or expected_state != payload.state:
        raise HTTPException(
            status_code=400,
            detail="This GitHub sign-in link is invalid or has expired. Please try again."
        )

    try:
        identity = oauth_service.fetch_github_identity(
            code=payload.code,
            redirect_uri=_github_redirect_uri(),
        )
    except oauth_service.GitHubOAuthError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    existing_user = (
        db.query(User)
        .filter(User.email == identity["email"])
        .first()
    )

    if existing_user:

        if not existing_user.is_active:
            raise HTTPException(
                status_code=401,
                detail="This account has been deactivated"
            )

        # Link this GitHub identity to the existing account the first
        # time it signs in this way, regardless of whether the account
        # was originally created with a password or a magic link -
        # both can add GitHub as an additional way in.
        if not existing_user.github_id:
            existing_user.github_id = identity["github_id"]

        user = existing_user
        audit_action = "user.github_login"

    else:

        # No invite-based join flow exists for any signup path yet
        # (see register_user above) - a brand-new GitHub sign-in gets
        # its own new organization, same as a brand-new password
        # registration does.
        organization = Organization(
            name=f"{identity['display_name']}'s Organization",
            slug=_unique_slug(db, _slugify(identity["display_name"])),
        )
        db.add(organization)
        db.flush()

        user = User(
            email=identity["email"],
            password_hash=None,
            auth_provider="github",
            github_id=identity["github_id"],
            role="admin",
            organization_id=organization.id,
        )
        db.add(user)
        db.flush()

        audit_action = "user.github_register"

    token = create_access_token({
        "sub": user.email
    })

    log_audit_event(
        db,
        organization_id=user.organization_id,
        action=audit_action,
        actor_user_id=user.id,
        actor_email=user.email,
    )
    db.commit()

    response = JSONResponse({
        "access_token": token,
        "token_type": "bearer"
    })
    response.delete_cookie(GITHUB_OAUTH_STATE_COOKIE)

    return response


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
