"""
Tests for column-level metadata: sample_values (auto-populated and
refreshed by scans/uploads) and description (a steward-authored
annotation, set only through PATCH /api/columns/{id} and never
touched by ingestion).
"""

import json
import unittest
import uuid
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import app


SCAN_RESULT_V1 = {
    "datasets": [{
        "schema_name": "public",
        "table_name": "widgets",
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

SCAN_RESULT_V2 = {
    "datasets": [{
        "schema_name": "public",
        "table_name": "widgets",
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
            "id": ["3", "4"],
            "email": ["z@y.com", "w@v.com"],
        },
    }],
    "foreign_keys": [],
}


class ColumnMetadataTests(unittest.TestCase):

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

    def _scan_and_get_columns(self, headers, scan_result):
        r = self.client.post("/api/sources", headers=headers, json={
            "name": f"Source {self._n}",
            "type": "postgresql",
            "connection_config": {"host": "x"},
        })
        source_id = r.json()["id"]

        with patch("app.api.scanner.get_scanner", return_value=lambda config: scan_result):
            r = self.client.post(f"/api/scanner/{source_id}", headers=headers)
        self.assertEqual(r.status_code, 200, r.text)

        r = self.client.get("/api/datasets", headers=headers)
        dataset_id = r.json()[0]["id"]

        r = self.client.get(f"/api/columns/dataset/{dataset_id}", headers=headers)
        self.assertEqual(r.status_code, 200, r.text)
        return source_id, dataset_id, {c["name"]: c for c in r.json()}

    def test_sample_values_populated_on_scan(self):
        headers = self._register_and_login(f"samp{self._n}@a.com", f"Samp Org {self._n}")

        _, _, columns = self._scan_and_get_columns(headers, SCAN_RESULT_V1)

        email_samples = json.loads(columns["email"]["sample_values"])
        self.assertEqual(email_samples, ["a@b.com", "c@d.com"])

    def test_sample_values_refresh_on_rescan(self):
        headers = self._register_and_login(f"resc{self._n}@a.com", f"Resc Org {self._n}")

        source_id, _, columns = self._scan_and_get_columns(headers, SCAN_RESULT_V1)
        self.assertEqual(json.loads(columns["id"]["sample_values"]), ["1", "2"])

        with patch("app.api.scanner.get_scanner", return_value=lambda config: SCAN_RESULT_V2):
            r = self.client.post(f"/api/scanner/{source_id}", headers=headers)
        self.assertEqual(r.status_code, 200, r.text)

        r = self.client.get("/api/datasets", headers=headers)
        dataset_id = r.json()[0]["id"]
        r = self.client.get(f"/api/columns/dataset/{dataset_id}", headers=headers)
        columns = {c["name"]: c for c in r.json()}

        self.assertEqual(json.loads(columns["id"]["sample_values"]), ["3", "4"])

    def test_steward_can_set_column_description(self):
        headers = self._register_and_login(f"desc{self._n}@a.com", f"Desc Org {self._n}")

        _, _, columns = self._scan_and_get_columns(headers, SCAN_RESULT_V1)
        column_id = columns["email"]["id"]
        self.assertIsNone(columns["email"]["description"])

        r = self.client.patch(
            f"/api/columns/{column_id}", headers=headers,
            json={"description": "Customer's primary contact email."},
        )
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["description"], "Customer's primary contact email.")

        r = self.client.get(f"/api/columns/dataset/{columns['email']['dataset_id']}", headers=headers)
        updated = {c["name"]: c for c in r.json()}
        self.assertEqual(updated["email"]["description"], "Customer's primary contact email.")

    def test_viewer_cannot_set_column_description(self):
        admin_headers = self._register_and_login(f"vwadmin{self._n}@a.com", f"Vw Org {self._n}")
        _, _, columns = self._scan_and_get_columns(admin_headers, SCAN_RESULT_V1)
        column_id = columns["email"]["id"]

        viewer_email = f"viewer{self._n}@a.com"
        self.client.post("/api/users", headers=admin_headers, json={
            "email": viewer_email,
            "password": "password123",
            "role": "viewer",
        })
        r = self.client.post("/api/auth/login", json={
            "email": viewer_email,
            "password": "password123",
        })
        viewer_headers = {"Authorization": f"Bearer {r.json()['access_token']}"}

        r = self.client.patch(
            f"/api/columns/{column_id}", headers=viewer_headers,
            json={"description": "Should not be allowed."},
        )
        self.assertEqual(r.status_code, 403)

    def test_column_description_update_is_tenant_scoped(self):
        headers_a = self._register_and_login(f"tenA{self._n}@a.com", f"Tenant A {self._n}")
        headers_b = self._register_and_login(f"tenB{self._n}@a.com", f"Tenant B {self._n}")

        _, _, columns = self._scan_and_get_columns(headers_a, SCAN_RESULT_V1)
        column_id = columns["email"]["id"]

        r = self.client.patch(
            f"/api/columns/{column_id}", headers=headers_b,
            json={"description": "Should not reach org A's column."},
        )
        self.assertEqual(r.status_code, 404)


if __name__ == "__main__":
    unittest.main()
