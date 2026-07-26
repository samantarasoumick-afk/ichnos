"""
Tests for column masking: a Data Owner/admin-only control over
whether a Viewer can see a column's real sample values, independent
of (and in addition to) classification. Classification says what a
column *is*; masking says who's actually allowed to see its values.
"""

import json
import unittest
import uuid
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import app


SCAN_RESULT = {
    "datasets": [{
        "schema_name": "public",
        "table_name": "customers",
        "columns": [
            ("id", "integer", "NO"),
            ("ssn", "text", "YES"),
        ],
        "row_count": 2,
        "column_stats": {
            "id": {"non_null": 2, "distinct": 2},
            "ssn": {"non_null": 2, "distinct": 2},
        },
        "column_samples": {
            "id": ["1", "2"],
            "ssn": ["123-45-6789", "987-65-4321"],
        },
    }],
    "foreign_keys": [],
}


class ColumnMaskingTests(unittest.TestCase):

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

    def _scan_and_get_columns(self, headers):
        r = self.client.post("/api/sources", headers=headers, json={
            "name": f"Source {self._n}",
            "type": "postgresql",
            "connection_config": {"host": "x"},
        })
        source_id = r.json()["id"]

        with patch("app.api.scanner.get_scanner", return_value=lambda config: SCAN_RESULT):
            r = self.client.post(f"/api/scanner/{source_id}", headers=headers)
        self.assertEqual(r.status_code, 200, r.text)

        r = self.client.get("/api/datasets", headers=headers)
        dataset_id = r.json()[0]["id"]

        r = self.client.get(f"/api/columns/dataset/{dataset_id}", headers=headers)
        self.assertEqual(r.status_code, 200, r.text)
        return dataset_id, {c["name"]: c for c in r.json()}

    def test_columns_are_unmasked_by_default(self):
        headers = self._register_and_login(f"def{self._n}@a.com", f"Def Org {self._n}")
        _, columns = self._scan_and_get_columns(headers)
        self.assertFalse(columns["ssn"]["masked"])

    def test_admin_can_mask_a_column(self):
        headers = self._register_and_login(f"adm{self._n}@a.com", f"Adm Org {self._n}")
        _, columns = self._scan_and_get_columns(headers)
        column_id = columns["ssn"]["id"]

        r = self.client.patch(
            f"/api/columns/{column_id}/masking", headers=headers,
            json={"masked": True},
        )
        self.assertEqual(r.status_code, 200, r.text)
        self.assertTrue(r.json()["masked"])

    def test_data_owner_can_mask_a_column(self):
        admin_headers = self._register_and_login(f"do{self._n}@a.com", f"DO Org {self._n}")
        _, columns = self._scan_and_get_columns(admin_headers)
        column_id = columns["ssn"]["id"]

        owner_headers = self._invite(admin_headers, f"owner{self._n}@a.com", "data_owner")

        r = self.client.patch(
            f"/api/columns/{column_id}/masking", headers=owner_headers,
            json={"masked": True},
        )
        self.assertEqual(r.status_code, 200, r.text)
        self.assertTrue(r.json()["masked"])

    def test_steward_cannot_mask_a_column(self):
        admin_headers = self._register_and_login(f"stw{self._n}@a.com", f"Stw Org {self._n}")
        _, columns = self._scan_and_get_columns(admin_headers)
        column_id = columns["ssn"]["id"]

        steward_headers = self._invite(admin_headers, f"steward{self._n}@a.com", "steward")

        r = self.client.patch(
            f"/api/columns/{column_id}/masking", headers=steward_headers,
            json={"masked": True},
        )
        self.assertEqual(r.status_code, 403)

    def test_viewer_cannot_mask_a_column(self):
        admin_headers = self._register_and_login(f"vwm{self._n}@a.com", f"Vwm Org {self._n}")
        _, columns = self._scan_and_get_columns(admin_headers)
        column_id = columns["ssn"]["id"]

        viewer_headers = self._invite(admin_headers, f"viewer{self._n}@a.com", "viewer")

        r = self.client.patch(
            f"/api/columns/{column_id}/masking", headers=viewer_headers,
            json={"masked": True},
        )
        self.assertEqual(r.status_code, 403)

    def test_viewer_sees_redacted_sample_values_for_masked_column(self):
        admin_headers = self._register_and_login(f"red{self._n}@a.com", f"Red Org {self._n}")
        dataset_id, columns = self._scan_and_get_columns(admin_headers)
        column_id = columns["ssn"]["id"]

        r = self.client.patch(
            f"/api/columns/{column_id}/masking", headers=admin_headers,
            json={"masked": True},
        )
        self.assertEqual(r.status_code, 200, r.text)

        viewer_headers = self._invite(admin_headers, f"viewer{self._n}@a.com", "viewer")

        r = self.client.get(f"/api/columns/dataset/{dataset_id}", headers=viewer_headers)
        self.assertEqual(r.status_code, 200, r.text)
        viewer_columns = {c["name"]: c for c in r.json()}

        self.assertTrue(viewer_columns["ssn"]["masked"])
        redacted = json.loads(viewer_columns["ssn"]["sample_values"])
        self.assertNotIn("123-45-6789", redacted)

        # An unmasked column on the same dataset is untouched.
        self.assertEqual(
            json.loads(viewer_columns["id"]["sample_values"]),
            ["1", "2"],
        )

    def test_admin_and_data_owner_still_see_real_values_when_masked(self):
        admin_headers = self._register_and_login(f"own{self._n}@a.com", f"Own Org {self._n}")
        dataset_id, columns = self._scan_and_get_columns(admin_headers)
        column_id = columns["ssn"]["id"]

        r = self.client.patch(
            f"/api/columns/{column_id}/masking", headers=admin_headers,
            json={"masked": True},
        )
        self.assertEqual(r.status_code, 200, r.text)

        owner_headers = self._invite(admin_headers, f"owner{self._n}@a.com", "data_owner")

        # Admin still sees the real values.
        r = self.client.get(f"/api/columns/dataset/{dataset_id}", headers=admin_headers)
        admin_columns = {c["name"]: c for c in r.json()}
        self.assertEqual(
            json.loads(admin_columns["ssn"]["sample_values"]),
            ["123-45-6789", "987-65-4321"],
        )

        # So does the Data Owner who set the mask.
        r = self.client.get(f"/api/columns/dataset/{dataset_id}", headers=owner_headers)
        owner_columns = {c["name"]: c for c in r.json()}
        self.assertEqual(
            json.loads(owner_columns["ssn"]["sample_values"]),
            ["123-45-6789", "987-65-4321"],
        )

    def test_column_masking_update_is_tenant_scoped(self):
        headers_a = self._register_and_login(f"tenA{self._n}@a.com", f"Tenant A {self._n}")
        headers_b = self._register_and_login(f"tenB{self._n}@a.com", f"Tenant B {self._n}")

        _, columns = self._scan_and_get_columns(headers_a)
        column_id = columns["ssn"]["id"]

        r = self.client.patch(
            f"/api/columns/{column_id}/masking", headers=headers_b,
            json={"masked": True},
        )
        self.assertEqual(r.status_code, 404)

    def test_masking_is_logged_to_audit_trail(self):
        headers = self._register_and_login(f"aud{self._n}@a.com", f"Aud Org {self._n}")
        _, columns = self._scan_and_get_columns(headers)
        column_id = columns["ssn"]["id"]

        r = self.client.patch(
            f"/api/columns/{column_id}/masking", headers=headers,
            json={"masked": True},
        )
        self.assertEqual(r.status_code, 200, r.text)

        r = self.client.get("/api/audit-log", headers=headers)
        self.assertEqual(r.status_code, 200, r.text)
        actions = [entry["action"] for entry in r.json()]
        self.assertIn("column.update_masking", actions)


if __name__ == "__main__":
    unittest.main()
