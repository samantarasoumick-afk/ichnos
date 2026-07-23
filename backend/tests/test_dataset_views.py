"""
Tests for dataset view/usage tracking: opening a dataset's detail page
records a (deduplicated) view, the catalog list endpoint does not,
distinct viewer count reflects unique people rather than raw
pageloads, and everything stays tenant-scoped.
"""

import unittest
import uuid
from unittest.mock import patch, MagicMock

from fastapi.testclient import TestClient

from app.db.database import SessionLocal
from app.main import app
from app.models.dataset_view import DatasetView


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


class DatasetViewTrackingTests(unittest.TestCase):

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

    def test_opening_detail_page_records_a_view(self):
        headers = self._register_and_login(f"v1{self._n}@a.com", f"Views Org 1 {self._n}")
        dataset_id = self._create_scanned_dataset(headers)

        r = self.client.get(f"/api/datasets/{dataset_id}", headers=headers)
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["view_count"], 1)
        self.assertEqual(r.json()["distinct_viewer_count"], 1)
        self.assertIsNotNone(r.json()["last_viewed_at"])

    def test_list_endpoint_does_not_record_a_view(self):
        headers = self._register_and_login(f"v2{self._n}@a.com", f"Views Org 2 {self._n}")
        dataset_id = self._create_scanned_dataset(headers)

        r = self.client.get("/api/datasets", headers=headers)
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()[0]["view_count"], 0)

        r = self.client.get(f"/api/datasets/{dataset_id}", headers=headers)
        self.assertEqual(r.json()["view_count"], 1)

    def test_repeat_views_within_window_are_deduplicated(self):
        headers = self._register_and_login(f"v3{self._n}@a.com", f"Views Org 3 {self._n}")
        dataset_id = self._create_scanned_dataset(headers)

        for _ in range(5):
            r = self.client.get(f"/api/datasets/{dataset_id}", headers=headers)
            self.assertEqual(r.status_code, 200, r.text)

        self.assertEqual(r.json()["view_count"], 1)

        db = SessionLocal()
        try:
            rows = db.query(DatasetView).filter(DatasetView.dataset_id == dataset_id).all()
            self.assertEqual(len(rows), 1)
        finally:
            db.close()

    def test_distinct_viewers_counts_unique_people_not_raw_views(self):
        headers_owner = self._register_and_login(f"v4o{self._n}@a.com", f"Views Org 4 {self._n}")
        dataset_id = self._create_scanned_dataset(headers_owner)

        r = self.client.post("/api/users", headers=headers_owner, json={
            "email": f"second{self._n}@a.com",
            "password": "password123",
            "role": "steward",
        })
        self.assertEqual(r.status_code, 200, r.text)

        r = self.client.post("/api/auth/login", json={
            "email": f"second{self._n}@a.com",
            "password": "password123",
        })
        headers_second = {"Authorization": f"Bearer {r.json()['access_token']}"}

        self.client.get(f"/api/datasets/{dataset_id}", headers=headers_owner)
        self.client.get(f"/api/datasets/{dataset_id}", headers=headers_owner)
        r = self.client.get(f"/api/datasets/{dataset_id}", headers=headers_second)

        self.assertEqual(r.json()["view_count"], 2)
        self.assertEqual(r.json()["distinct_viewer_count"], 2)

    def test_view_tracking_is_tenant_scoped(self):
        headers_a = self._register_and_login(f"v5a{self._n}@a.com", f"Views Org 5a {self._n}")
        headers_b = self._register_and_login(f"v5b{self._n}@a.com", f"Views Org 5b {self._n}")
        dataset_id = self._create_scanned_dataset(headers_a)

        r = self.client.get(f"/api/datasets/{dataset_id}", headers=headers_b)
        self.assertEqual(r.status_code, 404)

        r = self.client.get(f"/api/datasets/{dataset_id}", headers=headers_a)
        self.assertEqual(r.json()["view_count"], 1)


if __name__ == "__main__":
    unittest.main()
