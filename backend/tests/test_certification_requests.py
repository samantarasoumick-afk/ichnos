"""
Tests for the certification approval workflow: requesting
certification, admin approve/reject, the segregation-of-duties rule
(can't approve your own request unless you're the org's only admin),
duplicate-request prevention, and that direct edits to VERIFIED are
blocked on both existing governance endpoints - VERIFIED is only
reachable through an approved request.
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
        "columns": [("id", "integer", "NO")],
        "row_count": 1,
        "column_stats": {"id": {"non_null": 1, "distinct": 1}},
        "column_samples": {"id": ["1"]},
    }],
    "foreign_keys": [],
}


class CertificationRequestTests(unittest.TestCase):

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

    def _invite(self, admin_headers, email, role):
        r = self.client.post("/api/users", headers=admin_headers, json={
            "email": email,
            "password": "password123",
            "role": role,
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

    # ---------------------------
    # Direct-edit paths are blocked from reaching VERIFIED
    # ---------------------------

    def test_direct_certification_patch_to_verified_is_blocked(self):
        headers = self._register_and_login(f"cr1{self._n}@a.com", f"CertReq Org 1 {self._n}")
        dataset_id = self._create_scanned_dataset(headers)

        r = self.client.patch(f"/api/governance/datasets/{dataset_id}/certification", headers=headers, json={
            "certification": "VERIFIED"
        })
        self.assertEqual(r.status_code, 400)
        self.assertIn("certification request", r.json()["detail"])

    def test_direct_certification_patch_to_non_verified_still_works(self):
        headers = self._register_and_login(f"cr2{self._n}@a.com", f"CertReq Org 2 {self._n}")
        dataset_id = self._create_scanned_dataset(headers)

        r = self.client.patch(f"/api/governance/datasets/{dataset_id}/certification", headers=headers, json={
            "certification": "IN_REVIEW"
        })
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["certification"], "IN_REVIEW")

    def test_governance_update_to_verified_is_blocked(self):
        headers = self._register_and_login(f"cr3{self._n}@a.com", f"CertReq Org 3 {self._n}")
        dataset_id = self._create_scanned_dataset(headers)

        r = self.client.patch(f"/api/governance/datasets/{dataset_id}", headers=headers, json={
            "certification": "VERIFIED"
        })
        self.assertEqual(r.status_code, 400)

    # ---------------------------
    # Request lifecycle
    # ---------------------------

    def test_create_request_sets_dataset_to_in_review(self):
        admin_headers = self._register_and_login(f"cr4{self._n}@a.com", f"CertReq Org 4 {self._n}")
        dataset_id = self._create_scanned_dataset(admin_headers)

        r = self.client.post("/api/certification-requests", headers=admin_headers, json={
            "dataset_id": dataset_id,
            "request_note": "Looks ready to me",
        })
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["status"], "PENDING")

        r = self.client.get(f"/api/datasets/{dataset_id}", headers=admin_headers)
        self.assertEqual(r.json()["certification"], "IN_REVIEW")
        self.assertEqual(r.json()["pending_certification_request_id"], self.client.get(
            "/api/certification-requests", headers=admin_headers
        ).json()[0]["id"])

    def test_duplicate_pending_request_rejected(self):
        headers = self._register_and_login(f"cr5{self._n}@a.com", f"CertReq Org 5 {self._n}")
        dataset_id = self._create_scanned_dataset(headers)

        r = self.client.post("/api/certification-requests", headers=headers, json={"dataset_id": dataset_id})
        self.assertEqual(r.status_code, 200, r.text)

        r = self.client.post("/api/certification-requests", headers=headers, json={"dataset_id": dataset_id})
        self.assertEqual(r.status_code, 400)

    def test_steward_can_request_but_not_approve(self):
        admin_headers = self._register_and_login(f"cr6a{self._n}@a.com", f"CertReq Org 6 {self._n}")
        steward_headers = self._invite(admin_headers, f"cr6s{self._n}@a.com", "steward")
        dataset_id = self._create_scanned_dataset(admin_headers)

        r = self.client.post("/api/certification-requests", headers=steward_headers, json={"dataset_id": dataset_id})
        self.assertEqual(r.status_code, 200, r.text)
        request_id = r.json()["id"]

        r = self.client.post(f"/api/certification-requests/{request_id}/approve", headers=steward_headers, json={})
        self.assertEqual(r.status_code, 403)

    def test_second_admin_can_approve_and_dataset_becomes_verified(self):
        admin_headers = self._register_and_login(f"cr7a{self._n}@a.com", f"CertReq Org 7 {self._n}")
        second_admin_headers = self._invite(admin_headers, f"cr7b{self._n}@a.com", "admin")
        dataset_id = self._create_scanned_dataset(admin_headers)

        r = self.client.post("/api/certification-requests", headers=admin_headers, json={"dataset_id": dataset_id})
        request_id = r.json()["id"]

        r = self.client.post(
            f"/api/certification-requests/{request_id}/approve",
            headers=second_admin_headers,
            json={"review_note": "Confirmed with the source team"},
        )
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["status"], "APPROVED")

        r = self.client.get(f"/api/datasets/{dataset_id}", headers=admin_headers)
        self.assertEqual(r.json()["certification"], "VERIFIED")
        self.assertIsNone(r.json()["pending_certification_request_id"])

    def test_same_admin_cannot_approve_own_request_when_another_admin_exists(self):
        admin_headers = self._register_and_login(f"cr8a{self._n}@a.com", f"CertReq Org 8 {self._n}")
        self._invite(admin_headers, f"cr8b{self._n}@a.com", "admin")
        dataset_id = self._create_scanned_dataset(admin_headers)

        r = self.client.post("/api/certification-requests", headers=admin_headers, json={"dataset_id": dataset_id})
        request_id = r.json()["id"]

        r = self.client.post(f"/api/certification-requests/{request_id}/approve", headers=admin_headers, json={})
        self.assertEqual(r.status_code, 400)
        self.assertIn("own certification request", r.json()["detail"])

    def test_sole_admin_can_approve_own_request(self):
        admin_headers = self._register_and_login(f"cr9{self._n}@a.com", f"CertReq Org 9 {self._n}")
        dataset_id = self._create_scanned_dataset(admin_headers)

        r = self.client.post("/api/certification-requests", headers=admin_headers, json={"dataset_id": dataset_id})
        request_id = r.json()["id"]

        r = self.client.post(f"/api/certification-requests/{request_id}/approve", headers=admin_headers, json={})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["status"], "APPROVED")

    def test_reject_sends_dataset_back_to_draft(self):
        admin_headers = self._register_and_login(f"cr10a{self._n}@a.com", f"CertReq Org 10 {self._n}")
        second_admin_headers = self._invite(admin_headers, f"cr10b{self._n}@a.com", "admin")
        dataset_id = self._create_scanned_dataset(admin_headers)

        r = self.client.post("/api/certification-requests", headers=admin_headers, json={"dataset_id": dataset_id})
        request_id = r.json()["id"]

        r = self.client.post(
            f"/api/certification-requests/{request_id}/reject",
            headers=second_admin_headers,
            json={"review_note": "Missing a documented owner"},
        )
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["status"], "REJECTED")

        r = self.client.get(f"/api/datasets/{dataset_id}", headers=admin_headers)
        self.assertEqual(r.json()["certification"], "DRAFT")

    def test_approving_a_non_pending_request_rejected(self):
        admin_headers = self._register_and_login(f"cr11a{self._n}@a.com", f"CertReq Org 11 {self._n}")
        second_admin_headers = self._invite(admin_headers, f"cr11b{self._n}@a.com", "admin")
        dataset_id = self._create_scanned_dataset(admin_headers)

        r = self.client.post("/api/certification-requests", headers=admin_headers, json={"dataset_id": dataset_id})
        request_id = r.json()["id"]
        self.client.post(f"/api/certification-requests/{request_id}/approve", headers=second_admin_headers, json={})

        r = self.client.post(f"/api/certification-requests/{request_id}/approve", headers=second_admin_headers, json={})
        self.assertEqual(r.status_code, 400)

    def test_requests_are_tenant_scoped(self):
        headers_a = self._register_and_login(f"cr12a{self._n}@a.com", f"CertReq Org 12a {self._n}")
        headers_b = self._register_and_login(f"cr12b{self._n}@a.com", f"CertReq Org 12b {self._n}")
        dataset_id = self._create_scanned_dataset(headers_a)

        r = self.client.post("/api/certification-requests", headers=headers_b, json={"dataset_id": dataset_id})
        self.assertEqual(r.status_code, 404)

        self.client.post("/api/certification-requests", headers=headers_a, json={"dataset_id": dataset_id})
        r = self.client.get("/api/certification-requests", headers=headers_b)
        self.assertEqual(r.json(), [])

    def test_audit_log_records_lifecycle(self):
        admin_headers = self._register_and_login(f"cr13a{self._n}@a.com", f"CertReq Org 13 {self._n}")
        second_admin_headers = self._invite(admin_headers, f"cr13b{self._n}@a.com", "admin")
        dataset_id = self._create_scanned_dataset(admin_headers)

        r = self.client.post("/api/certification-requests", headers=admin_headers, json={"dataset_id": dataset_id})
        request_id = r.json()["id"]
        self.client.post(f"/api/certification-requests/{request_id}/approve", headers=second_admin_headers, json={})

        r = self.client.get("/api/audit-log", headers=admin_headers)
        actions = [entry["action"] for entry in r.json()]
        self.assertIn("certification_request.create", actions)
        self.assertIn("certification_request.approve", actions)


if __name__ == "__main__":
    unittest.main()
