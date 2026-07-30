"""
"Sign in with GitHub" - exchanges an OAuth authorization code for
GitHub's own access token, then fetches the authenticated user's
GitHub profile and a verified email address. This module only knows
how to talk to GitHub's API; it doesn't touch the User/Organization
models itself (that's app/api/auth.py's job - same division of labor
as email_service.py just sending mail, not deciding who gets one).

GITHUB_CLIENT_ID/GITHUB_CLIENT_SECRET are read at module import time
the same way SMTP_HOST/ANTHROPIC_API_KEY are, following this
codebase's "leave it unset and the feature degrades" convention -
except OAuth login has no degraded fallback mode. If the keys aren't
set, build_authorize_url() refuses outright rather than redirecting
the browser to a GitHub OAuth app that doesn't exist.

Uses `requests` (not `httpx`), matching stripe_scanner.py and
tableau_connector.py - the only two other places in this codebase
that call an external HTTP API directly.
"""

import os

from urllib.parse import urlencode

import requests


GITHUB_CLIENT_ID = os.getenv("GITHUB_CLIENT_ID")
GITHUB_CLIENT_SECRET = os.getenv("GITHUB_CLIENT_SECRET")

GITHUB_AUTHORIZE_URL = "https://github.com/login/oauth/authorize"
GITHUB_TOKEN_URL = "https://github.com/login/oauth/access_token"
GITHUB_USER_URL = "https://api.github.com/user"
GITHUB_USER_EMAILS_URL = "https://api.github.com/user/emails"

REQUEST_TIMEOUT_SECONDS = 15


class GitHubOAuthError(Exception):
    """
    Raised for anything that keeps a GitHub sign-in from completing:
    the provider not configured on this instance, a rejected/expired
    code, an unreachable GitHub API, or a GitHub account with no
    verified email to sign in with. Callers in app/api/auth.py turn
    this into a 400/503 - a failed OAuth handshake is a user-facing
    "try again" case, not a server bug.
    """


def is_configured() -> bool:
    return bool(GITHUB_CLIENT_ID and GITHUB_CLIENT_SECRET)


def build_authorize_url(redirect_uri: str, state: str) -> str:

    if not is_configured():
        raise GitHubOAuthError(
            "Sign in with GitHub isn't configured on this instance "
            "(GITHUB_CLIENT_ID/GITHUB_CLIENT_SECRET are unset)."
        )

    params = {
        "client_id": GITHUB_CLIENT_ID,
        "redirect_uri": redirect_uri,
        # read:user for the profile, user:email since a GitHub
        # account's email can be private - without this scope
        # /user/emails comes back empty even for a verified address.
        "scope": "read:user user:email",
        "state": state,
    }

    return f"{GITHUB_AUTHORIZE_URL}?{urlencode(params)}"


def _github_api_headers(access_token: str) -> dict:
    return {
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/vnd.github+json",
        # GitHub's API rejects requests with no User-Agent.
        "User-Agent": "DatFe-App",
    }


def _exchange_code_for_token(code: str, redirect_uri: str) -> str:

    try:
        response = requests.post(
            GITHUB_TOKEN_URL,
            data={
                "client_id": GITHUB_CLIENT_ID,
                "client_secret": GITHUB_CLIENT_SECRET,
                "code": code,
                "redirect_uri": redirect_uri,
            },
            headers={"Accept": "application/json"},
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
    except requests.RequestException as exc:
        raise GitHubOAuthError(
            f"Unable to reach GitHub to complete sign-in: {exc}"
        )

    if response.status_code != 200:
        raise GitHubOAuthError(
            f"GitHub rejected the sign-in code ({response.status_code}): "
            f"{response.text[:300]}"
        )

    try:
        payload = response.json()
    except ValueError as exc:
        raise GitHubOAuthError(
            f"Unexpected response from GitHub during sign-in: {exc}"
        )

    access_token = payload.get("access_token")

    if not access_token:
        reason = payload.get("error_description") or payload.get("error") or "no access token returned"
        raise GitHubOAuthError(f"GitHub sign-in failed: {reason}")

    return access_token


def _fetch_profile(access_token: str) -> dict:

    try:
        response = requests.get(
            GITHUB_USER_URL,
            headers=_github_api_headers(access_token),
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
    except requests.RequestException as exc:
        raise GitHubOAuthError(
            f"Unable to reach GitHub to fetch your profile: {exc}"
        )

    if response.status_code != 200:
        raise GitHubOAuthError(
            f"GitHub rejected the profile request ({response.status_code}): "
            f"{response.text[:300]}"
        )

    try:
        return response.json()
    except ValueError as exc:
        raise GitHubOAuthError(f"Unexpected profile response from GitHub: {exc}")


def _fetch_verified_primary_email(access_token: str):
    """
    Falls back to this when the profile's own `email` field is null -
    GitHub only fills that in when the account's email is public.
    Returns None (rather than raising) on anything short of a clean
    200, so a scope/permission hiccup here degrades to "no email
    found" and lets the caller produce one clear error message instead
    of two different failure paths.
    """

    try:
        response = requests.get(
            GITHUB_USER_EMAILS_URL,
            headers=_github_api_headers(access_token),
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
    except requests.RequestException:
        return None

    if response.status_code != 200:
        return None

    try:
        emails = response.json()
    except ValueError:
        return None

    for entry in emails:
        if entry.get("primary") and entry.get("verified"):
            return entry.get("email")

    for entry in emails:
        if entry.get("verified"):
            return entry.get("email")

    return None


def fetch_github_identity(code: str, redirect_uri: str) -> dict:
    """
    Full code -> verified identity exchange. Returns
    {"github_id": str, "email": str, "display_name": str}. Raises
    GitHubOAuthError if any step fails, or if no verified email can be
    found at all - DatFe accounts are keyed by email, so sign-in
    isn't possible without one (GitHub accounts can have a private,
    unverified, or entirely absent email).
    """

    if not is_configured():
        raise GitHubOAuthError("Sign in with GitHub isn't configured on this instance.")

    access_token = _exchange_code_for_token(code, redirect_uri)
    profile = _fetch_profile(access_token)

    email = profile.get("email") or _fetch_verified_primary_email(access_token)

    if not email:
        raise GitHubOAuthError(
            "Your GitHub account doesn't have a verified email address to "
            "sign in with. Add and verify one on GitHub (or make an "
            "existing one public) and try again."
        )

    github_id = profile.get("id")

    if github_id is None:
        raise GitHubOAuthError("Unexpected profile response from GitHub (missing id).")

    return {
        "github_id": str(github_id),
        "email": email,
        "display_name": profile.get("name") or profile.get("login") or "GitHub User",
    }
