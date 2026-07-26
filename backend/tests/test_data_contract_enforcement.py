"""
Tests for Data Contract enforcement beyond schema-only logging:
(A) DQ threshold enforcement - a contract can set
    quality_thresholds.min_overall_score, checked against the
    dataset's DataQuality.overall_score on every scan/upload, in the
    same evaluate_contract() pass as schema checks.
(B) Lineage breach propagation - GET
    /api/data-contracts/dataset/{id}/upstream-breaches surfaces any
    upstream (via lineage) dataset with an ACTIVE, BREACHED contract.
"""

import unittest
import uuid
from unittest.mock import patch, MagicMock

from fastapi.testclient import TestClient

from app.main import app


# Overall score works out to exactly 100: every ratio (completeness,
# uniqueness, validity, consistency) is 1.0, freshness is always 100.
SCAN_PERFECT_QUALITY = {
    "datasets": [{
        "schema_name": "public",
        "table_name": "customers",
        "columns": [
            ("id", "integer", "NO"),
            ("email", "text", "YES"),
        ],
        "row_count": 2,
        "column_stats": {
            "id": {"non_null": 2, "distinct": 2},
            "email": {"non_null": 2, "distinct": 2},
        },
        "column_samples": {
            "id": ["1", "2"],
            "email": ["a@b.com", "c@d.com"],
        },
    }],
    "foreign_keys": [],
}

# Overall score works out to exactly 75: completeness avg = (1.0 + 0.5)
# / 2 = 75%, uniqueness = 100%, validity = 0% (email samples don't
# match the email pattern), consistency = 100% (id is numeric and
# parses), freshness = 100% -> (75+100+0+100+100)/5 = 75.
SCAN_LOW_QUALITY = {
    "datasets": [{
        "schema_name": "public",
        "table_name": "customers",
        "columns": [
            ("id", "integer", "NO"),
            ("email", "text", "YES"),
        ],
        "row_count": 4,
        "column_stats": {
            "id": {"non_null": 4, "distinct": 4},
            "email": {"non_null": 2, "distinct": 2},
        },
        "column_samples": {
            "id": ["1", "2", "3", "4"],
            "email": ["not-an-email", "also-not-one"],
        },
    }],
    "foreign_keys": [],
}

# A second, unrelated dataset (a downstream report) with no quality
# issues of its own - used for lineage propagation tests.
SCAN_DOWNSTREAM = {
    "datasets": [{
        "schema_name": "public",
        "table_name": "customer_report",
        "columns": [
            ("id", "integer", "NO"),
        ],
        "row_count": 2,
        "column_stats": {
            "id": {"non_null": 2, "distinct": 2},
        },
        "column_samples": {
            "id": ["1", "2"],
        },
    }],
    "foreign_keys": [],
}


class DataContractEnforcementTests(unittest.TestCase):

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

    def _create_scanned_dataset(self, headers, scan_result, source_name=None):
        with patch("app.api.scanner.get_scanner") as mock_get_scanner:
            mock_scan = MagicMock(return_value=scan_result)
            mock_get_scanner.return_value = mock_scan

            r = self.client.post("/api/sources", headers=headers, json={
                "name": source_name or f"Source {self._n}",
                "type": "postgresql",
                "connection_config": {"host": "x", "database": "y", "user": "z", "password": "p"},
            })
            self.assertEqual(r.status_code, 200, r.text)
            source_id = r.json()["id"]

            r = self.client.post(f"/api/scanner/{source_id}", headers=headers)
            self.assertEqual(r.status_code, 200, r.text)

        return source_id, mock_scan

    def _dataset_by_table_name(self, headers, table_name):
        r = self.client.get("/api/datasets", headers=headers)
        matches = [d for d in r.json() if d["name"] == table_name]
        self.assertEqual(len(matches), 1, r.text)
        return matches[0]["id"]

    def _contract_payload(self, dataset_id, min_overall_score, columns=None):
        return {
            "dataset_id": dataset_id,
            "owner": "Data Platform Team",
            "schema_expectations": {"columns": columns or []},
            "quality_thresholds": {"min_overall_score": min_overall_score},
        }

    # ---------------------------
    # (A) DQ threshold enforcement
    # ---------------------------

    def test_contract_with_dq_threshold_compliant_when_score_meets_minimum(self):
        headers = self._register_and_login(f"dq1{self._n}@a.com", f"DQ Org 1 {self._n}")
        self._create_scanned_dataset(headers, SCAN_PERFECT_QUALITY)
        dataset_id = self._dataset_by_table_name(headers, "customers")

        r = self.client.post(
            "/api/data-contracts", headers=headers,
            json=self._contract_payload(dataset_id, min_overall_score=90),
        )
        contract_id = r.json()["id"]

        r = self.client.post(f"/api/data-contracts/{contract_id}/activate", headers=headers)
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["last_status"], "COMPLIANT")

    def test_contract_with_dq_threshold_breaches_when_score_below_minimum(self):
        headers = self._register_and_login(f"dq2{self._n}@a.com", f"DQ Org 2 {self._n}")
        self._create_scanned_dataset(headers, SCAN_LOW_QUALITY)
        dataset_id = self._dataset_by_table_name(headers, "customers")

        r = self.client.post(
            "/api/data-contracts", headers=headers,
            json=self._contract_payload(dataset_id, min_overall_score=90),
        )
        contract_id = r.json()["id"]

        r = self.client.post(f"/api/data-contracts/{contract_id}/activate", headers=headers)
        self.assertEqual(r.status_code, 200, r.text)
        body = r.json()
        self.assertEqual(body["last_status"], "BREACHED")
        self.assertIn("75", body["last_breach_details"])
        self.assertIn("90", body["last_breach_details"])

        r = self.client.get("/api/audit-log", headers=headers)
        actions = [entry["action"] for entry in r.json()]
        self.assertIn("contract.breach", actions)

    def test_dq_breach_and_schema_breach_both_reported_together(self):
        headers = self._register_and_login(f"dq3{self._n}@a.com", f"DQ Org 3 {self._n}")
        self._create_scanned_dataset(headers, SCAN_LOW_QUALITY)
        dataset_id = self._dataset_by_table_name(headers, "customers")

        r = self.client.post(
            "/api/data-contracts", headers=headers,
            json=self._contract_payload(
                dataset_id, min_overall_score=90,
                columns=[{"name": "phone", "required": True}],
            ),
        )
        contract_id = r.json()["id"]

        r = self.client.post(f"/api/data-contracts/{contract_id}/activate", headers=headers)
        self.assertEqual(r.status_code, 200, r.text)
        details = r.json()["last_breach_details"]
        self.assertIn("phone", details)
        self.assertIn("90", details)

    def test_rescan_recovering_quality_returns_contract_to_compliant(self):
        headers = self._register_and_login(f"dq4{self._n}@a.com", f"DQ Org 4 {self._n}")
        source_id, mock_scan = self._create_scanned_dataset(headers, SCAN_LOW_QUALITY)
        dataset_id = self._dataset_by_table_name(headers, "customers")

        r = self.client.post(
            "/api/data-contracts", headers=headers,
            json=self._contract_payload(dataset_id, min_overall_score=90),
        )
        contract_id = r.json()["id"]
        r = self.client.post(f"/api/data-contracts/{contract_id}/activate", headers=headers)
        self.assertEqual(r.json()["last_status"], "BREACHED")

        with patch("app.api.scanner.get_scanner") as mock_get_scanner:
            mock_get_scanner.return_value = MagicMock(return_value=SCAN_PERFECT_QUALITY)
            r = self.client.post(f"/api/scanner/{source_id}", headers=headers)
        self.assertEqual(r.status_code, 200, r.text)

        r = self.client.get(f"/api/data-contracts/dataset/{dataset_id}", headers=headers)
        contract = [c for c in r.json() if c["id"] == contract_id][0]
        self.assertEqual(contract["last_status"], "COMPLIANT")

    # ---------------------------
    # (B) Lineage breach propagation
    # ---------------------------

    def test_downstream_dataset_sees_upstream_contract_breach(self):
        headers = self._register_and_login(f"lb1{self._n}@a.com", f"Lineage Breach Org 1 {self._n}")

        self._create_scanned_dataset(headers, SCAN_LOW_QUALITY, source_name=f"Upstream {self._n}")
        upstream_id = self._dataset_by_table_name(headers, "customers")

        self._create_scanned_dataset(headers, SCAN_DOWNSTREAM, source_name=f"Downstream {self._n}")
        downstream_id = self._dataset_by_table_name(headers, "customer_report")

        r = self.client.post(
            "/api/data-contracts", headers=headers,
            json=self._contract_payload(upstream_id, min_overall_score=90),
        )
        contract_id = r.json()["id"]
        r = self.client.post(f"/api/data-contracts/{contract_id}/activate", headers=headers)
        self.assertEqual(r.json()["last_status"], "BREACHED")

        # Downstream has no breach visible yet - no lineage edge exists.
        r = self.client.get(
            f"/api/data-contracts/dataset/{downstream_id}/upstream-breaches", headers=headers
        )
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json(), [])

        # Wire the lineage edge: upstream -> downstream.
        r = self.client.post("/api/lineage", headers=headers, json={
            "upstream_dataset_id": upstream_id,
            "downstream_dataset_id": downstream_id,
            "transformation_type": "AGGREGATION",
        })
        self.assertEqual(r.status_code, 200, r.text)

        r = self.client.get(
            f"/api/data-contracts/dataset/{downstream_id}/upstream-breaches", headers=headers
        )
        self.assertEqual(r.status_code, 200, r.text)
        breaches = r.json()
        self.assertEqual(len(breaches), 1)
        self.assertEqual(breaches[0]["dataset_id"], upstream_id)
        self.assertEqual(breaches[0]["dataset_name"], "customers")
        self.assertIn("90", breaches[0]["breach_details"])

        # The upstream dataset itself reports no *upstream* breaches -
        # it's the source of the problem, not a consumer of one.
        r = self.client.get(
            f"/api/data-contracts/dataset/{upstream_id}/upstream-breaches", headers=headers
        )
        self.assertEqual(r.json(), [])

    def test_no_upstream_breach_when_upstream_contract_is_compliant(self):
        headers = self._register_and_login(f"lb2{self._n}@a.com", f"Lineage Breach Org 2 {self._n}")

        self._create_scanned_dataset(headers, SCAN_PERFECT_QUALITY, source_name=f"Upstream {self._n}")
        upstream_id = self._dataset_by_table_name(headers, "customers")

        self._create_scanned_dataset(headers, SCAN_DOWNSTREAM, source_name=f"Downstream {self._n}")
        downstream_id = self._dataset_by_table_name(headers, "customer_report")

        r = self.client.post(
            "/api/data-contracts", headers=headers,
            json=self._contract_payload(upstream_id, min_overall_score=50),
        )
        contract_id = r.json()["id"]
        r = self.client.post(f"/api/data-contracts/{contract_id}/activate", headers=headers)
        self.assertEqual(r.json()["last_status"], "COMPLIANT")

        self.client.post("/api/lineage", headers=headers, json={
            "upstream_dataset_id": upstream_id,
            "downstream_dataset_id": downstream_id,
        })

        r = self.client.get(
            f"/api/data-contracts/dataset/{downstream_id}/upstream-breaches", headers=headers
        )
        self.assertEqual(r.json(), [])

    def test_upstream_breaches_endpoint_is_tenant_scoped(self):
        headers_a = self._register_and_login(f"lb3a{self._n}@a.com", f"Tenant A {self._n}")
        headers_b = self._register_and_login(f"lb3b{self._n}@a.com", f"Tenant B {self._n}")

        self._create_scanned_dataset(headers_a, SCAN_LOW_QUALITY)
        dataset_id = self._dataset_by_table_name(headers_a, "customers")

        r = self.client.get(
            f"/api/data-contracts/dataset/{dataset_id}/upstream-breaches", headers=headers_b
        )
        self.assertEqual(r.status_code, 404)


if __name__ == "__main__":
    unittest.main()
