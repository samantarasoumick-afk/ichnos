"""
Tests for the org-level governance maturity score (GET /api/maturity):
the NOT_STARTED case for a brand-new org, the fully-covered case
(steward, certification, active contract, documented purpose all in
place), the partially-covered case's recommended_next_steps, and
tenant scoping.
"""

import unittest
import uuid
from unittest.mock import patch, MagicMock

from fastapi.testclient import TestClient

from app.main import app


SCAN_RESULT = {
    "datasets": [{
        "schema_name": "public",
        "table_name": "customers",
        "columns": [
            ("id", "integer", "NO"),
            ("email", "text", "YES"),
            ("phone", "text", "YES"),
        ],
        "row_count": 2,
        "column_stats": {
            "id": {"non_null": 2, "distinct": 2},
            "email": {"non_null": 2, "distinct": 2},
            "phone": {"non_null": 2, "distinct": 2},
        },
        "column_samples": {
            "id": ["1", "2"],
            "email": ["a@b.com", "c@d.com"],
            "phone": ["9876543210", "9123456780"],
        },
    }],
    "foreign_keys": [],
}


class MaturityTests(unittest.TestCase):

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

    @patch("app.api.scanner.get_scanner")
    def _create_scanned_dataset(self, headers, mock_get_scanner):
        mock_get_scanner.return_value = MagicMock(return_value=SCAN_RESULT)

        r = self.client.post("/api/sources", headers=headers, json={
            "name": f"Source {self._n}",
            "type": "postgresql",
            "connection_config": {"host": "x", "database": "y", "user": "z", "password": "p"},
        })
        source_id = r.json()["id"]

        r = self.client.post(f"/api/scanner/{source_id}", headers=headers)
        self.assertEqual(r.status_code, 200, r.text)

        return self.client.get("/api/datasets", headers=headers).json()[0]["id"]

    def test_org_with_no_datasets_is_not_started(self):
        headers = self._register_and_login(f"m1{self._n}@a.com", f"Maturity Org 1 {self._n}")

        r = self.client.get("/api/maturity", headers=headers)
        self.assertEqual(r.status_code, 200, r.text)
        body = r.json()

        self.assertEqual(body["total_datasets"], 0)
        self.assertEqual(body["level"], "NOT_STARTED")
        self.assertEqual(body["overall_score"], 0)
        self.assertTrue(len(body["recommended_next_steps"]) >= 1)
        self.assertIn("Connect your first data source", body["recommended_next_steps"][0])

    def test_fully_covered_dataset_scores_high_with_no_gaps_recommended(self):
        headers = self._register_and_login(f"m2{self._n}@a.com", f"Maturity Org 2 {self._n}")
        dataset_id = self._create_scanned_dataset(headers)

        # This dataset has email+phone -> both PII -> sensitivity HIGH,
        # so it's "PII-bearing" and needs a documented purpose to be
        # fully covered.
        r = self.client.get(f"/api/governance/datasets/{dataset_id}/scorecard", headers=headers)
        self.assertEqual(r.json()["sensitivity_score"], "HIGH")

        r = self.client.patch(f"/api/governance/datasets/{dataset_id}", headers=headers, json={
            "steward": "Alex",
            "purpose": "Customer support and order fulfillment",
        })
        self.assertEqual(r.status_code, 200, r.text)

        # Certification now goes through the approval workflow -
        # this org only has one admin, so they can approve their own
        # request (see test_certification_requests.py for the
        # multi-admin segregation-of-duties behavior).
        r = self.client.post("/api/certification-requests", headers=headers, json={"dataset_id": dataset_id})
        self.assertEqual(r.status_code, 200, r.text)
        request_id = r.json()["id"]

        r = self.client.post(f"/api/certification-requests/{request_id}/approve", headers=headers, json={})
        self.assertEqual(r.status_code, 200, r.text)

        r = self.client.post("/api/data-contracts", headers=headers, json={
            "dataset_id": dataset_id,
            "schema_expectations": {"columns": [{"name": "id", "required": True}]},
        })
        contract_id = r.json()["id"]
        r = self.client.post(f"/api/data-contracts/{contract_id}/activate", headers=headers)
        self.assertEqual(r.status_code, 200, r.text)

        r = self.client.get("/api/maturity", headers=headers)
        self.assertEqual(r.status_code, 200, r.text)
        body = r.json()

        self.assertEqual(body["total_datasets"], 1)
        self.assertEqual(body["coverage"]["pct_with_steward"], 100)
        self.assertEqual(body["coverage"]["pct_certified"], 100)
        self.assertEqual(body["coverage"]["pct_with_active_contract"], 100)
        self.assertEqual(body["coverage"]["pct_pii_with_documented_purpose"], 100)
        self.assertIn(body["level"], ("MANAGED", "TRUSTED"))
        self.assertNotIn(
            "Assign a steward", " ".join(body["recommended_next_steps"])
        )

    def test_uncovered_dataset_recommends_gaps(self):
        headers = self._register_and_login(f"m3{self._n}@a.com", f"Maturity Org 3 {self._n}")
        self._create_scanned_dataset(headers)

        r = self.client.get("/api/maturity", headers=headers)
        self.assertEqual(r.status_code, 200, r.text)
        body = r.json()

        self.assertEqual(body["coverage"]["pct_with_steward"], 0)
        self.assertEqual(body["coverage"]["pct_certified"], 0)
        self.assertEqual(body["coverage"]["pct_with_active_contract"], 0)
        # Coverage is 0% across the board, but governance/quality
        # scores degrade gracefully rather than as binary flags, so
        # this doesn't necessarily bottom out at AD_HOC - the point
        # here is the gaps are visible and called out, not a specific
        # threshold crossing.
        self.assertIn(body["level"], ("AD_HOC", "REACTIVE"))

        joined = " ".join(body["recommended_next_steps"])
        self.assertIn("steward", joined.lower())

    def test_maturity_is_tenant_scoped(self):
        headers_a = self._register_and_login(f"m4a{self._n}@a.com", f"Maturity Org 4a {self._n}")
        headers_b = self._register_and_login(f"m4b{self._n}@a.com", f"Maturity Org 4b {self._n}")

        self._create_scanned_dataset(headers_a)

        r = self.client.get("/api/maturity", headers=headers_b)
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["total_datasets"], 0)
        self.assertEqual(r.json()["level"], "NOT_STARTED")

        r = self.client.get("/api/maturity", headers=headers_a)
        self.assertEqual(r.json()["total_datasets"], 1)


if __name__ == "__main__":
    unittest.main()
