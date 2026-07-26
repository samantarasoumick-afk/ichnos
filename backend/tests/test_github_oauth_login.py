"""
"Sign in with GitHub": GET /api/auth/oauth/github/start redirects to
GitHub's consent screen (and sets a short-lived state cookie), and
POST /api/auth/oauth/github/callback exchanges the code GitHub hands
back for a verified identity, then either signs in an existing user
(linking github_id the first time) or creates a brand-new user + org,
exactly like /api/auth/register does for a first-time password
signup. There's no live GitHub account in this environment, so every
call to app.services.oauth_service.requests is mocked - see
test_stripe_connector.py for the same mocking approach against a
different external API.
"""

import unittest
import uuid
from unittest.mock import MagicMock, patch
from urllib.parse import parse_qs, urlparse

from fastapi.testclient import TestClient

from app.main import app
from app.db.database import SessionLocal
from app.models.organization import Organization
from app.models.user import User
from app.services import oauth_service
from app.api.auth import GITHUB_OAUTH_STATE_COOKIE


def _response(status_code=200, json_body=None, text=""):
    response = MagicMock()
    response.status_code = status_code
    response.json.return_value = json_body if json_body is not None else {}
    response.text = text
    return response


def _configured_github():
    return patch.multiple(
        oauth_service,
        GITHUB_CLIENT_ID="test-client-id",
        GITHUB_CLIENT_SECRET="test-client-secret",
    )


TOKEN_RESPONSE = _response(json_body={"access_token": "gho_test123", "token_type": "bearer"})


def _profile_response(github_id=99001, email="octocat@example.com", name="The Octocat", login="octocat"):
    return _response(json_body={"id": github_id, "email": email, "name": name, "login": login})


class GitHubOAuthStartTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)

    def test_returns_503_when_not_configured(self):
        with patch.multiple(oauth_service, GITHUB_CLIENT_ID=None, GITHUB_CLIENT_SECRET=None):
            r = self.client.get("/api/auth/oauth/github/start", follow_redirects=False)
            self.assertEqual(r.status_code, 503, r.text)

    def test_redirects_to_github_and_sets_state_cookie_when_configured(self):
        with _configured_github():
            r = self.client.get("/api/auth/oauth/github/start", follow_redirects=False)

        self.assertIn(r.status_code, (302, 307), r.text)

        location = r.headers["location"]
        parsed = urlparse(location)
        self.assertEqual(f"{parsed.scheme}://{parsed.netloc}{parsed.path}", "https://github.com/login/oauth/authorize")

        query = parse_qs(parsed.query)
        self.assertEqual(query["client_id"], ["test-client-id"])
        self.assertIn("login/github/callback", query["redirect_uri"][0])
        self.assertTrue(query["state"][0])

        self.assertIn(GITHUB_OAUTH_STATE_COOKIE, r.cookies)
        self.assertEqual(r.cookies[GITHUB_OAUTH_STATE_COOKIE], query["state"][0])


class GitHubOAuthCallbackTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)

    def setUp(self):
        self._n = uuid.uuid4().hex[:8]

    def _start_and_get_state(self):
        with _configured_github():
            r = self.client.get("/api/auth/oauth/github/start", follow_redirects=False)
        state = parse_qs(urlparse(r.headers["location"]).query)["state"][0]
        # The TestClient's own cookie jar already picked up the
        # Set-Cookie from the /start response, so it'll be sent
        # automatically on the callback POST below - mirroring a real
        # browser carrying the cookie across the GitHub redirect.
        return state

    def test_first_time_signin_creates_new_user_and_org(self):
        state = self._start_and_get_state()
        email = f"newgh{self._n}@example.com"

        with _configured_github(), patch("app.services.oauth_service.requests.post") as mock_post, \
                patch("app.services.oauth_service.requests.get") as mock_get:
            mock_post.return_value = TOKEN_RESPONSE
            mock_get.return_value = _profile_response(github_id=555000 + int(self._n, 16) % 1000, email=email, name="New Ghi")

            r = self.client.post(
                "/api/auth/oauth/github/callback",
                json={"code": "test-code", "state": state},
            )

        self.assertEqual(r.status_code, 200, r.text)
        self.assertIn("access_token", r.json())

        headers = {"Authorization": f"Bearer {r.json()['access_token']}"}
        me = self.client.get("/api/auth/me", headers=headers)
        self.assertEqual(me.status_code, 200, me.text)
        self.assertEqual(me.json()["email"], email)
        self.assertEqual(me.json()["role"], "admin")
        self.assertIn("New Ghi", me.json()["organization_name"])

        db = SessionLocal()
        try:
            user = db.query(User).filter(User.email == email).first()
            self.assertIsNotNone(user)
            self.assertEqual(user.auth_provider, "github")
            self.assertIsNone(user.password_hash)
            self.assertTrue(user.github_id)
        finally:
            db.close()

    def test_existing_password_user_is_linked_by_email_not_duplicated(self):
        email = f"linkme{self._n}@example.com"

        r = self.client.post("/api/auth/register", json={
            "email": email,
            "password": "password123",
            "organization_name": f"Link Org {self._n}",
        })
        self.assertEqual(r.status_code, 200, r.text)

        db = SessionLocal()
        try:
            org_count_before = db.query(Organization).count()
        finally:
            db.close()

        state = self._start_and_get_state()

        with _configured_github(), patch("app.services.oauth_service.requests.post") as mock_post, \
                patch("app.services.oauth_service.requests.get") as mock_get:
            mock_post.return_value = TOKEN_RESPONSE
            mock_get.return_value = _profile_response(github_id=777000 + int(self._n, 16) % 1000, email=email)

            r = self.client.post(
                "/api/auth/oauth/github/callback",
                json={"code": "test-code", "state": state},
            )

        self.assertEqual(r.status_code, 200, r.text)

        db = SessionLocal()
        try:
            org_count_after = db.query(Organization).count()
            user = db.query(User).filter(User.email == email).first()
            self.assertEqual(org_count_before, org_count_after)
            self.assertTrue(user.github_id)
            self.assertEqual(user.auth_provider, "password")  # unchanged - just linked, not converted
        finally:
            db.close()

    def test_missing_or_mismatched_state_is_rejected(self):
        with _configured_github(), patch("app.services.oauth_service.requests.post") as mock_post, \
                patch("app.services.oauth_service.requests.get") as mock_get:
            mock_post.return_value = TOKEN_RESPONSE
            mock_get.return_value = _profile_response()

            r = self.client.post(
                "/api/auth/oauth/github/callback",
                json={"code": "test-code", "state": "not-the-real-state"},
            )

        self.assertEqual(r.status_code, 400, r.text)
        mock_post.assert_not_called()

    def test_falls_back_to_emails_endpoint_when_profile_email_is_private(self):
        state = self._start_and_get_state()
        email = f"privateemail{self._n}@example.com"

        with _configured_github(), patch("app.services.oauth_service.requests.post") as mock_post, \
                patch("app.services.oauth_service.requests.get") as mock_get:
            mock_post.return_value = TOKEN_RESPONSE
            mock_get.side_effect = [
                _profile_response(github_id=888000 + int(self._n, 16) % 1000, email=None),
                _response(json_body=[
                    {"email": "old@example.com", "primary": False, "verified": True},
                    {"email": email, "primary": True, "verified": True},
                ]),
            ]

            r = self.client.post(
                "/api/auth/oauth/github/callback",
                json={"code": "test-code", "state": state},
            )

        self.assertEqual(r.status_code, 200, r.text)

        headers = {"Authorization": f"Bearer {r.json()['access_token']}"}
        me = self.client.get("/api/auth/me", headers=headers)
        self.assertEqual(me.json()["email"], email)

    def test_no_verified_email_available_is_rejected(self):
        state = self._start_and_get_state()

        with _configured_github(), patch("app.services.oauth_service.requests.post") as mock_post, \
                patch("app.services.oauth_service.requests.get") as mock_get:
            mock_post.return_value = TOKEN_RESPONSE
            mock_get.side_effect = [
                _profile_response(github_id=999000 + int(self._n, 16) % 1000, email=None),
                _response(json_body=[{"email": "unverified@example.com", "primary": True, "verified": False}]),
            ]

            r = self.client.post(
                "/api/auth/oauth/github/callback",
                json={"code": "test-code", "state": state},
            )

        self.assertEqual(r.status_code, 400, r.text)
        self.assertIn("verified email", r.json()["detail"])

    def test_github_only_account_cannot_password_login(self):
        state = self._start_and_get_state()
        email = f"githubonly{self._n}@example.com"

        with _configured_github(), patch("app.services.oauth_service.requests.post") as mock_post, \
                patch("app.services.oauth_service.requests.get") as mock_get:
            mock_post.return_value = TOKEN_RESPONSE
            mock_get.return_value = _profile_response(github_id=222000 + int(self._n, 16) % 1000, email=email)

            r = self.client.post(
                "/api/auth/oauth/github/callback",
                json={"code": "test-code", "state": state},
            )
        self.assertEqual(r.status_code, 200, r.text)

        login = self.client.post("/api/auth/login", json={"email": email, "password": "anything123"})
        self.assertEqual(login.status_code, 401, login.text)

    def test_deactivated_github_linked_account_cannot_sign_in(self):
        email = f"deactivatedgh{self._n}@example.com"

        r = self.client.post("/api/auth/register", json={
            "email": email,
            "password": "password123",
            "organization_name": f"Deactivated GH Org {self._n}",
        })
        self.assertEqual(r.status_code, 200, r.text)

        db = SessionLocal()
        try:
            user = db.query(User).filter(User.email == email).first()
            user.is_active = False
            db.commit()
        finally:
            db.close()

        state = self._start_and_get_state()

        with _configured_github(), patch("app.services.oauth_service.requests.post") as mock_post, \
                patch("app.services.oauth_service.requests.get") as mock_get:
            mock_post.return_value = TOKEN_RESPONSE
            mock_get.return_value = _profile_response(github_id=333000 + int(self._n, 16) % 1000, email=email)

            r = self.client.post(
                "/api/auth/oauth/github/callback",
                json={"code": "test-code", "state": state},
            )

        self.assertEqual(r.status_code, 401, r.text)

    def test_github_rejecting_the_code_produces_a_clean_400(self):
        state = self._start_and_get_state()

        with _configured_github(), patch("app.services.oauth_service.requests.post") as mock_post:
            mock_post.return_value = _response(status_code=400, json_body={"error": "bad_verification_code"})

            r = self.client.post(
                "/api/auth/oauth/github/callback",
                json={"code": "bad-code", "state": state},
            )

        self.assertEqual(r.status_code, 400, r.text)


if __name__ == "__main__":
    unittest.main()
