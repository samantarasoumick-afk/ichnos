"""
Regression test for GET /api/columns/dataset/{id}: it used to compare
DatasetColumn.dataset_id (a String column) against a raw uuid.UUID
object rather than str(uuid), so the filter never matched anything
and the endpoint silently returned an empty list for every dataset -
even ones with columns. Caught by seeding realistic demo data and
noticing the "Columns" section was empty on every dataset detail page.
"""

import unittest
import uuid
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import app


SCAN_RESULT = {
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


class ColumnsByDatasetEndpointTests(unittest.TestCase):

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
    def test_columns_by_dataset_returns_the_datasets_columns(self, mock_get_scanner):
        mock_get_scanner.return_value = lambda config: SCAN_RESULT

        headers = self._register_and_login(f"cols{self._n}@a.com", f"Cols Org {self._n}")

        r = self.client.post("/api/sources", headers=headers, json={
            "name": f"Source {self._n}",
            "type": "postgresql",
            "connection_config": {"host": "x"},
        })
        source_id = r.json()["id"]

        r = self.client.post(f"/api/scanner/{source_id}", headers=headers)
        self.assertEqual(r.status_code, 200, r.text)

        r = self.client.get("/api/datasets", headers=headers)
        dataset_id = r.json()[0]["id"]

        r = self.client.get(f"/api/columns/dataset/{dataset_id}", headers=headers)
        self.assertEqual(r.status_code, 200, r.text)
        names = {c["name"] for c in r.json()}
        self.assertEqual(names, {"id", "email"})

    def test_invalid_dataset_id_returns_400(self):
        headers = self._register_and_login(f"badid{self._n}@a.com", f"BadId Org {self._n}")

        r = self.client.get("/api/columns/dataset/not-a-uuid", headers=headers)
        self.assertEqual(r.status_code, 400)


if __name__ == "__main__":
    unittest.main()
