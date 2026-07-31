"""
Tests for the per-user home-dashboard metrics preference: a user picks
which KPI cards they want to see, stored as a JSON-encoded list of
metric keys on User.dashboard_metrics. No preference saved yet should
read back as metrics=None (frontend falls back to its own defaults),
distinct from an explicit empty selection.
"""

import unittest
import uuid

from fastapi.testclient import TestClient

from app.main import app


class DashboardMetricsPreferenceTests(unittest.TestCase):

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
        return {"Authorization": f"Bearer {r.json()['access_token']}"}

    def test_no_preference_saved_yet_returns_null(self):
        headers = self._register_and_login(f"dm1{self._n}@a.com", f"Dashboard Org 1 {self._n}")

        r = self.client.get("/api/users/me/dashboard-metrics", headers=headers)
        self.assertEqual(r.status_code, 200, r.text)
        self.assertIsNone(r.json()["metrics"])

    def test_save_and_read_back_preference(self):
        headers = self._register_and_login(f"dm2{self._n}@a.com", f"Dashboard Org 2 {self._n}")

        chosen = ["total_datasets", "avg_privacy_score", "breached_contracts"]
        r = self.client.put(
            "/api/users/me/dashboard-metrics",
            headers=headers,
            json={"metrics": chosen},
        )
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["metrics"], chosen)

        r = self.client.get("/api/users/me/dashboard-metrics", headers=headers)
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["metrics"], chosen)

    def test_explicit_empty_selection_is_distinct_from_no_preference(self):
        headers = self._register_and_login(f"dm3{self._n}@a.com", f"Dashboard Org 3 {self._n}")

        r = self.client.put(
            "/api/users/me/dashboard-metrics",
            headers=headers,
            json={"metrics": []},
        )
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["metrics"], [])

        r = self.client.get("/api/users/me/dashboard-metrics", headers=headers)
        self.assertEqual(r.status_code, 200, r.text)
        # An explicit empty list, not None - the person really did
        # choose "show nothing," which is different from never having
        # set a preference.
        self.assertEqual(r.json()["metrics"], [])

    def test_preference_is_scoped_to_the_saving_user(self):
        headers_a = self._register_and_login(f"dm4a{self._n}@a.com", f"Dashboard Org 4 {self._n}")

        r = self.client.put(
            "/api/users/me/dashboard-metrics",
            headers=headers_a,
            json={"metrics": ["total_datasets"]},
        )
        self.assertEqual(r.status_code, 200, r.text)

        headers_b = self._register_and_login(f"dm4b{self._n}@a.com", f"Dashboard Org 5 {self._n}")
        r = self.client.get("/api/users/me/dashboard-metrics", headers=headers_b)
        self.assertEqual(r.status_code, 200, r.text)
        self.assertIsNone(r.json()["metrics"])


if __name__ == "__main__":
    unittest.main()
