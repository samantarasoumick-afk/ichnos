"""
Every brand-new organization now starts with the full demo estate
already loaded by default, regardless of which signup path created it
- password registration (app/api/auth.py's register_user) or a
first-time GitHub sign-in (github_oauth_callback). See
_seed_demo_data_for_new_org's docstring in app/api/auth.py for the
reasoning: a first-time admin should land on a catalog with something
to explore immediately, and can clear it themselves (POST
/api/demo/clear, unchanged) whenever they're ready to connect real
sources.

tests/conftest.py turns this default off for the whole test session
(most other test files register throwaway orgs expecting a genuinely
empty starting catalog) - every class below patches the
AUTO_SEED_DEMO_DATA_ON_SIGNUP env var back to "true" for its own
tests, since this file's whole job is to exercise the feature itself.
"""

import os
import unittest
import uuid
from unittest.mock import MagicMock, patch
from urllib.parse import parse_qs, urlparse

from fastapi.testclient import TestClient

from app.main import app
from app.services import oauth_service


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


def _profile_response(github_id, email, name="New Ghi"):
    return _response(json_body={"id": github_id, "email": email, "name": name, "login": "octocat"})


@patch.dict(os.environ, {"AUTO_SEED_DEMO_DATA_ON_SIGNUP": "true"})
class PasswordRegistrationAutoSeedTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)

    def setUp(self):
        self._n = uuid.uuid4().hex[:8]

    def _register_and_login(self, email, org_name):
        r = self.client.post("/api/auth/register", json={
            "email": email,
            "password": "password123",
            "organization_name": org_name,
        })
        self.assertEqual(r.status_code, 200, r.text)

        r = self.client.post("/api/auth/login", json={
            "email": email,
            "password": "password123",
        })
        self.assertEqual(r.status_code, 200, r.text)

        return {"Authorization": f"Bearer {r.json()['access_token']}"}

    def test_registration_auto_seeds_demo_data(self):
        headers = self._register_and_login(f"seed1{self._n}@a.com", f"Auto Seed Org 1 {self._n}")

        r = self.client.get("/api/demo/status", headers=headers)
        self.assertEqual(r.status_code, 200, r.text)

        body = r.json()
        self.assertTrue(body["demo_data_loaded"])
        self.assertEqual(body["demo_source_count"], 6)

    def test_auto_seeded_data_shows_up_in_the_catalog_immediately(self):
        headers = self._register_and_login(f"seed2{self._n}@a.com", f"Auto Seed Org 2 {self._n}")

        r = self.client.get("/api/sources", headers=headers)
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(len(r.json()), 6)
        self.assertTrue(all(s["is_seed_data"] for s in r.json()))

    def test_auto_seeded_data_can_be_cleared(self):
        headers = self._register_and_login(f"seed3{self._n}@a.com", f"Auto Seed Org 3 {self._n}")

        r = self.client.post("/api/demo/clear", headers=headers)
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["sources_removed"], 6)

        r = self.client.get("/api/demo/status", headers=headers)
        self.assertFalse(r.json()["demo_data_loaded"])
        self.assertEqual(r.json()["demo_source_count"], 0)

        r = self.client.get("/api/sources", headers=headers)
        self.assertEqual(r.json(), [])

    def test_re_seeding_after_a_clear_works_normally(self):
        headers = self._register_and_login(f"seed4{self._n}@a.com", f"Auto Seed Org 4 {self._n}")

        self.client.post("/api/demo/clear", headers=headers)

        r = self.client.post("/api/demo/seed", headers=headers)
        self.assertEqual(r.status_code, 200, r.text)

        r = self.client.get("/api/demo/status", headers=headers)
        self.assertTrue(r.json()["demo_data_loaded"])


class PasswordRegistrationAutoSeedDisabledByDefaultInTestsTests(unittest.TestCase):
    """
    Sanity check on the gate itself, run with the suite's normal
    (unpatched) environment: without opting back in, registration
    behaves exactly like it always has in this test suite - empty
    catalog, no auto-seed.
    """

    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)

    def setUp(self):
        self._n = uuid.uuid4().hex[:8]

    def test_registration_does_not_auto_seed_when_flag_is_off(self):
        r = self.client.post("/api/auth/register", json={
            "email": f"noseed{self._n}@a.com",
            "password": "password123",
            "organization_name": f"No Seed Org {self._n}",
        })
        self.assertEqual(r.status_code, 200, r.text)

        r = self.client.post("/api/auth/login", json={
            "email": f"noseed{self._n}@a.com",
            "password": "password123",
        })
        headers = {"Authorization": f"Bearer {r.json()['access_token']}"}

        status = self.client.get("/api/demo/status", headers=headers)
        self.assertFalse(status.json()["demo_data_loaded"])


@patch.dict(os.environ, {"AUTO_SEED_DEMO_DATA_ON_SIGNUP": "true"})
class GitHubFirstTimeSignupAutoSeedTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)

    def setUp(self):
        self._n = uuid.uuid4().hex[:8]

    def _start_and_get_state(self):
        with _configured_github():
            r = self.client.get("/api/auth/oauth/github/start", follow_redirects=False)
        return parse_qs(urlparse(r.headers["location"]).query)["state"][0]

    def test_first_time_github_signup_auto_seeds_demo_data(self):
        state = self._start_and_get_state()
        email = f"ghseed{self._n}@example.com"

        with _configured_github(), patch("app.services.oauth_service.requests.post") as mock_post, \
                patch("app.services.oauth_service.requests.get") as mock_get:
            mock_post.return_value = TOKEN_RESPONSE
            mock_get.return_value = _profile_response(
                github_id=444000 + int(self._n, 16) % 1000, email=email
            )

            r = self.client.post(
                "/api/auth/oauth/github/callback",
                json={"code": "test-code", "state": state},
            )

        self.assertEqual(r.status_code, 200, r.text)
        headers = {"Authorization": f"Bearer {r.json()['access_token']}"}

        status = self.client.get("/api/demo/status", headers=headers)
        self.assertTrue(status.json()["demo_data_loaded"])
        self.assertEqual(status.json()["demo_source_count"], 6)

    def test_linking_github_to_an_existing_account_does_not_reseed(self):
        # This account's organization was already auto-seeded once, by
        # the password registration itself - linking GitHub as a
        # second way in for the *same* existing user (not a new org)
        # must not seed a second time on top of it.
        email = f"ghlink{self._n}@example.com"

        r = self.client.post("/api/auth/register", json={
            "email": email,
            "password": "password123",
            "organization_name": f"GH Link Org {self._n}",
        })
        self.assertEqual(r.status_code, 200, r.text)

        state = self._start_and_get_state()

        with _configured_github(), patch("app.services.oauth_service.requests.post") as mock_post, \
                patch("app.services.oauth_service.requests.get") as mock_get:
            mock_post.return_value = TOKEN_RESPONSE
            mock_get.return_value = _profile_response(
                github_id=555999 + int(self._n, 16) % 1000, email=email
            )

            r = self.client.post(
                "/api/auth/oauth/github/callback",
                json={"code": "test-code", "state": state},
            )

        self.assertEqual(r.status_code, 200, r.text)
        headers = {"Authorization": f"Bearer {r.json()['access_token']}"}

        status = self.client.get("/api/demo/status", headers=headers)
        # Still 6, not 12 - proof the link path didn't seed a second time.
        self.assertEqual(status.json()["demo_source_count"], 6)


if __name__ == "__main__":
    unittest.main()
