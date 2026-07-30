"""
Tests for the Ecosystem View's onboarding progress tracker
(app/services/onboarding_service.py, GET/POST /api/ecosystem/onboarding/*)
- what makes the "10 days instead of 3 months" claim measurable.
"""

import unittest
import uuid

from fastapi.testclient import TestClient

from app.main import app


class OnboardingApiTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)

    def setUp(self):
        self._n = uuid.uuid4().hex[:8]

    def _register_and_login(self, email, org_name):
        r = self.client.post("/api/auth/register", json={
            "email": email, "password": "password123", "organization_name": org_name,
        })
        self.assertEqual(r.status_code, 200, r.text)
        r = self.client.post("/api/auth/login", json={"email": email, "password": "password123"})
        return {"Authorization": f"Bearer {r.json()['access_token']}"}

    def test_fresh_user_has_zero_progress(self):
        headers = self._register_and_login(f"onb{self._n}@a.com", f"Onboarding Org {self._n}")
        r = self.client.get("/api/ecosystem/onboarding/progress", headers=headers)
        self.assertEqual(r.status_code, 200, r.text)
        body = r.json()
        self.assertEqual(body["completed_count"], 0)
        self.assertEqual(body["percent_complete"], 0)
        self.assertIsNone(body["ramp_days"])
        self.assertEqual(len(body["milestones"]), 6)
        self.assertTrue(all(not m["completed"] for m in body["milestones"]))

    def test_recording_a_milestone_updates_progress(self):
        headers = self._register_and_login(f"onbrec{self._n}@a.com", f"Onboarding Rec Org {self._n}")
        r = self.client.post("/api/ecosystem/onboarding/milestones/VIEWED_ECOSYSTEM_MAP", headers=headers)
        self.assertEqual(r.status_code, 200, r.text)
        body = r.json()
        self.assertEqual(body["completed_count"], 1)
        viewed = next(m for m in body["milestones"] if m["key"] == "VIEWED_ECOSYSTEM_MAP")
        self.assertTrue(viewed["completed"])
        self.assertIsNotNone(viewed["achieved_at"])

    def test_recording_the_same_milestone_twice_is_idempotent(self):
        headers = self._register_and_login(f"onbdup{self._n}@a.com", f"Onboarding Dup Org {self._n}")
        r1 = self.client.post("/api/ecosystem/onboarding/milestones/USED_SEMANTIC_SEARCH", headers=headers)
        r2 = self.client.post("/api/ecosystem/onboarding/milestones/USED_SEMANTIC_SEARCH", headers=headers)
        self.assertEqual(r1.status_code, 200, r1.text)
        self.assertEqual(r2.status_code, 200, r2.text)
        self.assertEqual(r2.json()["completed_count"], 1)

    def test_unknown_milestone_returns_404(self):
        headers = self._register_and_login(f"onbunknown{self._n}@a.com", f"Onboarding Unknown Org {self._n}")
        r = self.client.post("/api/ecosystem/onboarding/milestones/NOT_A_REAL_MILESTONE", headers=headers)
        self.assertEqual(r.status_code, 404, r.text)

    def test_completing_all_milestones_reports_percent_and_ramp_days(self):
        headers = self._register_and_login(f"onbfull{self._n}@a.com", f"Onboarding Full Org {self._n}")

        milestone_keys = [
            "VIEWED_ECOSYSTEM_MAP",
            "EXPLORED_FRONT_OFFICE",
            "EXPLORED_MIDDLE_OFFICE",
            "EXPLORED_BACK_OFFICE",
            "TRACED_PROVENANCE",
            "USED_SEMANTIC_SEARCH",
        ]
        body = None
        for key in milestone_keys:
            r = self.client.post(f"/api/ecosystem/onboarding/milestones/{key}", headers=headers)
            self.assertEqual(r.status_code, 200, r.text)
            body = r.json()

        self.assertEqual(body["completed_count"], 6)
        self.assertEqual(body["percent_complete"], 100)
        # All hit "today" in this test, so the measured ramp is a
        # single calendar day - the whole point is that it's *measured*,
        # not hardcoded to any particular number.
        self.assertEqual(body["ramp_days"], 1)

    def test_progress_is_per_user_not_shared_across_org(self):
        email_a = f"onbusera{self._n}@a.com"
        email_b = f"onbuserb{self._n}@a.com"
        headers_a = self._register_and_login(email_a, f"Onboarding Shared Org {self._n}")

        self.client.post(
            "/api/users",
            headers=headers_a,
            json={"email": email_b, "password": "password123", "role": "viewer"},
        )
        r = self.client.post("/api/auth/login", json={"email": email_b, "password": "password123"})
        headers_b = {"Authorization": f"Bearer {r.json()['access_token']}"}

        self.client.post("/api/ecosystem/onboarding/milestones/VIEWED_ECOSYSTEM_MAP", headers=headers_a)

        r = self.client.get("/api/ecosystem/onboarding/progress", headers=headers_b)
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["completed_count"], 0)

    def test_onboarding_endpoints_require_auth(self):
        r = self.client.get("/api/ecosystem/onboarding/progress")
        self.assertEqual(r.status_code, 401, r.text)
        r = self.client.post("/api/ecosystem/onboarding/milestones/VIEWED_ECOSYSTEM_MAP")
        self.assertEqual(r.status_code, 401, r.text)


if __name__ == "__main__":
    unittest.main()
