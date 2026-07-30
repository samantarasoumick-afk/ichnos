"""
Tests for the Data Contracts feature (Phase 1: schema-level contracts
+ breach logging): CRUD/lifecycle of a DataContract (DRAFT -> ACTIVE ->
DEPRECATED, versioning, tenant scoping), and the automatic evaluation
that runs against a dataset's real columns every time it's scanned or
uploaded, via the same ingest_dataset_info() hook used by every
connector.
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

# "phone" dropped from the source - if a contract requires it, this
# scan should trip a breach.
SCAN_MISSING_PHONE = {
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


class DataContractsTests(unittest.TestCase):

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
    def _create_scanned_dataset(self, headers, mock_get_scanner, scan_result=SCAN_RESULT):
        mock_scan = MagicMock(return_value=scan_result)
        mock_get_scanner.return_value = mock_scan

        r = self.client.post("/api/sources", headers=headers, json={
            "name": f"Source {self._n}",
            "type": "postgresql",
            "connection_config": {"host": "x", "database": "y", "user": "z", "password": "p"},
        })
        self.assertEqual(r.status_code, 200, r.text)
        source_id = r.json()["id"]

        r = self.client.post(f"/api/scanner/{source_id}", headers=headers)
        self.assertEqual(r.status_code, 200, r.text)

        r = self.client.get("/api/datasets", headers=headers)
        dataset_id = r.json()[0]["id"]

        return source_id, dataset_id, mock_scan

    def _contract_payload(self, dataset_id, columns=None):
        if columns is None:
            columns = [
                {"name": "id", "data_type": "integer", "nullable": False, "required": True},
                {"name": "email", "required": True},
                {"name": "phone", "required": True},
            ]
        return {
            "dataset_id": dataset_id,
            "owner": "Data Platform Team",
            "schema_expectations": {"columns": columns},
        }

    # ---------------------------
    # CRUD / lifecycle
    # ---------------------------

    def test_create_contract_starts_as_draft_with_no_evaluation(self):
        headers = self._register_and_login(f"c1{self._n}@a.com", f"Contracts Org 1 {self._n}")
        _source_id, dataset_id, _mock = self._create_scanned_dataset(headers)

        r = self.client.post("/api/data-contracts", headers=headers, json=self._contract_payload(dataset_id))
        self.assertEqual(r.status_code, 200, r.text)
        body = r.json()
        self.assertEqual(body["status"], "DRAFT")
        self.assertEqual(body["version"], 1)
        self.assertIsNone(body["last_status"])

        # A DRAFT contract isn't active yet, so the dataset shouldn't
        # report anything but NO_CONTRACT.
        r = self.client.get("/api/datasets", headers=headers)
        self.assertEqual(r.json()[0]["contract_status"], "NO_CONTRACT")

    def test_create_contract_requires_admin_or_steward(self):
        headers = self._register_and_login(f"c2{self._n}@a.com", f"Contracts Org 2 {self._n}")
        _source_id, dataset_id, _mock = self._create_scanned_dataset(headers)

        r = self.client.post("/api/users", headers=headers, json={
            "email": f"viewer{self._n}@a.com",
            "password": "password123",
            "role": "viewer",
        })
        self.assertEqual(r.status_code, 200, r.text)

        r = self.client.post("/api/auth/login", json={
            "email": f"viewer{self._n}@a.com",
            "password": "password123",
        })
        viewer_headers = {"Authorization": f"Bearer {r.json()['access_token']}"}

        r = self.client.post("/api/data-contracts", headers=viewer_headers, json=self._contract_payload(dataset_id))
        self.assertEqual(r.status_code, 403)

    def test_create_contract_for_dataset_in_other_org_returns_404(self):
        headers_a = self._register_and_login(f"c3a{self._n}@a.com", f"Contracts Org 3a {self._n}")
        headers_b = self._register_and_login(f"c3b{self._n}@a.com", f"Contracts Org 3b {self._n}")
        _source_id, dataset_id, _mock = self._create_scanned_dataset(headers_a)

        r = self.client.post("/api/data-contracts", headers=headers_b, json=self._contract_payload(dataset_id))
        self.assertEqual(r.status_code, 404)

    def test_update_draft_contract_succeeds(self):
        headers = self._register_and_login(f"c4{self._n}@a.com", f"Contracts Org 4 {self._n}")
        _source_id, dataset_id, _mock = self._create_scanned_dataset(headers)

        r = self.client.post("/api/data-contracts", headers=headers, json=self._contract_payload(dataset_id))
        contract_id = r.json()["id"]

        r = self.client.patch(f"/api/data-contracts/{contract_id}", headers=headers, json={
            "owner": "New Owner"
        })
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["owner"], "New Owner")

    def test_update_non_draft_contract_rejected(self):
        headers = self._register_and_login(f"c5{self._n}@a.com", f"Contracts Org 5 {self._n}")
        _source_id, dataset_id, _mock = self._create_scanned_dataset(headers)

        r = self.client.post("/api/data-contracts", headers=headers, json=self._contract_payload(dataset_id))
        contract_id = r.json()["id"]

        r = self.client.post(f"/api/data-contracts/{contract_id}/activate", headers=headers)
        self.assertEqual(r.status_code, 200, r.text)

        r = self.client.patch(f"/api/data-contracts/{contract_id}", headers=headers, json={"owner": "Nope"})
        self.assertEqual(r.status_code, 400)

    def test_activate_evaluates_immediately_and_reports_compliant(self):
        email = f"c6{self._n}@a.com"
        headers = self._register_and_login(email, f"Contracts Org 6 {self._n}")
        _source_id, dataset_id, _mock = self._create_scanned_dataset(headers)

        r = self.client.post("/api/data-contracts", headers=headers, json=self._contract_payload(dataset_id))
        contract_id = r.json()["id"]
        self.assertIsNone(r.json()["activated_by_email"])
        self.assertIsNone(r.json()["activated_at"])

        r = self.client.post(f"/api/data-contracts/{contract_id}/activate", headers=headers)
        self.assertEqual(r.status_code, 200, r.text)
        body = r.json()
        self.assertEqual(body["status"], "ACTIVE")
        self.assertEqual(body["last_status"], "COMPLIANT")
        self.assertIsNotNone(body["last_evaluated_at"])
        # Who actually enforced this contract, and when - a persisted
        # fact on the row itself, not just an audit-log entry.
        self.assertEqual(body["activated_by_email"], email)
        self.assertIsNotNone(body["activated_at"])

        r = self.client.get("/api/datasets", headers=headers)
        self.assertEqual(r.json()[0]["contract_status"], "COMPLIANT")

    def test_activate_deprecates_previous_active_version(self):
        headers = self._register_and_login(f"c7{self._n}@a.com", f"Contracts Org 7 {self._n}")
        _source_id, dataset_id, _mock = self._create_scanned_dataset(headers)

        r = self.client.post("/api/data-contracts", headers=headers, json=self._contract_payload(dataset_id))
        first_contract_id = r.json()["id"]
        r = self.client.post(f"/api/data-contracts/{first_contract_id}/activate", headers=headers)
        self.assertEqual(r.status_code, 200, r.text)

        # Author and activate a v2.
        r = self.client.post("/api/data-contracts", headers=headers, json=self._contract_payload(dataset_id))
        second_contract_id = r.json()["id"]
        self.assertEqual(r.json()["version"], 2)

        r = self.client.post(f"/api/data-contracts/{second_contract_id}/activate", headers=headers)
        self.assertEqual(r.status_code, 200, r.text)

        r = self.client.get(f"/api/data-contracts/dataset/{dataset_id}", headers=headers)
        contracts_by_id = {c["id"]: c for c in r.json()}
        self.assertEqual(contracts_by_id[first_contract_id]["status"], "DEPRECATED")
        self.assertEqual(contracts_by_id[second_contract_id]["status"], "ACTIVE")

    def test_activate_non_draft_rejected(self):
        headers = self._register_and_login(f"c8{self._n}@a.com", f"Contracts Org 8 {self._n}")
        _source_id, dataset_id, _mock = self._create_scanned_dataset(headers)

        r = self.client.post("/api/data-contracts", headers=headers, json=self._contract_payload(dataset_id))
        contract_id = r.json()["id"]
        self.client.post(f"/api/data-contracts/{contract_id}/activate", headers=headers)

        r = self.client.post(f"/api/data-contracts/{contract_id}/activate", headers=headers)
        self.assertEqual(r.status_code, 400)

    def test_deprecate_active_contract(self):
        headers = self._register_and_login(f"c9{self._n}@a.com", f"Contracts Org 9 {self._n}")
        _source_id, dataset_id, _mock = self._create_scanned_dataset(headers)

        r = self.client.post("/api/data-contracts", headers=headers, json=self._contract_payload(dataset_id))
        contract_id = r.json()["id"]
        self.client.post(f"/api/data-contracts/{contract_id}/activate", headers=headers)

        r = self.client.post(f"/api/data-contracts/{contract_id}/deprecate", headers=headers)
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["status"], "DEPRECATED")

        r = self.client.get("/api/datasets", headers=headers)
        self.assertEqual(r.json()[0]["contract_status"], "NO_CONTRACT")

    def test_deprecate_non_active_rejected(self):
        headers = self._register_and_login(f"c10{self._n}@a.com", f"Contracts Org 10 {self._n}")
        _source_id, dataset_id, _mock = self._create_scanned_dataset(headers)

        r = self.client.post("/api/data-contracts", headers=headers, json=self._contract_payload(dataset_id))
        contract_id = r.json()["id"]

        r = self.client.post(f"/api/data-contracts/{contract_id}/deprecate", headers=headers)
        self.assertEqual(r.status_code, 400)

    # ---------------------------
    # Automatic evaluation on scan
    # ---------------------------

    @patch("app.api.scanner.get_scanner")
    def test_rescan_that_drops_a_required_column_breaches_and_logs_audit(self, mock_get_scanner):
        headers = self._register_and_login(f"c11{self._n}@a.com", f"Contracts Org 11 {self._n}")

        mock_scan = MagicMock(return_value=SCAN_RESULT)
        mock_get_scanner.return_value = mock_scan

        r = self.client.post("/api/sources", headers=headers, json={
            "name": f"Source {self._n}",
            "type": "postgresql",
            "connection_config": {"host": "x", "database": "y", "user": "z", "password": "p"},
        })
        source_id = r.json()["id"]

        r = self.client.post(f"/api/scanner/{source_id}", headers=headers)
        self.assertEqual(r.status_code, 200, r.text)
        dataset_id = self.client.get("/api/datasets", headers=headers).json()[0]["id"]

        r = self.client.post("/api/data-contracts", headers=headers, json=self._contract_payload(dataset_id))
        contract_id = r.json()["id"]

        r = self.client.post(f"/api/data-contracts/{contract_id}/activate", headers=headers)
        self.assertEqual(r.json()["last_status"], "COMPLIANT")

        # Rescan with "phone" gone - the contract requires it.
        mock_scan.return_value = SCAN_MISSING_PHONE
        r = self.client.post(f"/api/scanner/{source_id}", headers=headers)
        self.assertEqual(r.status_code, 200, r.text)

        r = self.client.get(f"/api/data-contracts/dataset/{dataset_id}", headers=headers)
        contract = r.json()[0]
        self.assertEqual(contract["last_status"], "BREACHED")
        self.assertIn("phone", contract["last_breach_details"])

        r = self.client.get("/api/datasets", headers=headers)
        self.assertEqual(r.json()[0]["contract_status"], "BREACHED")

        r = self.client.get("/api/audit-log", headers=headers)
        actions = [entry["action"] for entry in r.json()]
        self.assertIn("contract.breach", actions)

    def test_nullable_violation_is_detected(self):
        headers = self._register_and_login(f"c12{self._n}@a.com", f"Contracts Org 12 {self._n}")
        _source_id, dataset_id, _mock = self._create_scanned_dataset(headers)

        # "email" scanned as nullable=YES, but the contract demands
        # NOT NULL - should breach even though the column is present.
        payload = self._contract_payload(dataset_id, columns=[
            {"name": "id", "required": True},
            {"name": "email", "nullable": False, "required": True},
        ])
        r = self.client.post("/api/data-contracts", headers=headers, json=payload)
        contract_id = r.json()["id"]

        r = self.client.post(f"/api/data-contracts/{contract_id}/activate", headers=headers)
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["last_status"], "BREACHED")
        self.assertIn("email", r.json()["last_breach_details"])

    def test_deactivated_dataset_with_no_active_contract_is_pending_or_no_contract(self):
        headers = self._register_and_login(f"c13{self._n}@a.com", f"Contracts Org 13 {self._n}")
        _source_id, dataset_id, _mock = self._create_scanned_dataset(headers)

        r = self.client.get("/api/datasets", headers=headers)
        self.assertEqual(r.json()[0]["contract_status"], "NO_CONTRACT")


if __name__ == "__main__":
    unittest.main()
