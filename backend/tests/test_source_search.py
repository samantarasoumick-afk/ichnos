"""
Sources are now a first-class searchable/tiered entity alongside
datasets and columns (app/services/catalog_search_service.py's
_source_document(), app/api/search.py's per-tier result reservation).
Covers: a source itself shows up in GET /api/search with a rollup
subtitle and an /ecosystem?sourceId=... url, and a query matching all
three tiers (source/dataset/column) actually returns all three rather
than one type crowding the others out of a small limit.
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


class SourceSearchTests(unittest.TestCase):

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

    @patch("app.api.scanner.get_scanner")
    def _create_and_scan_source(self, headers, name, scan_result, mock_get_scanner):
        mock_get_scanner.return_value = MagicMock(return_value=scan_result)

        r = self.client.post("/api/sources", headers=headers, json={
            "name": name,
            "type": "postgresql",
            "connection_config": {"host": "x", "database": "y", "user": "z", "password": "p"},
        })
        self.assertEqual(r.status_code, 200, r.text)
        source_id = r.json()["id"]

        r = self.client.post(f"/api/scanner/{source_id}", headers=headers)
        self.assertEqual(r.status_code, 200, r.text)

        return source_id

    def test_source_result_has_rollup_subtitle_and_ecosystem_url(self):
        headers = self._register_and_login(f"src1{self._n}@a.com", f"Source Search Org 1 {self._n}")

        source_name = f"SalesforceCRM{self._n}"
        source_id = self._create_and_scan_source(headers, source_name, SCAN_RESULT)

        r = self.client.get(f"/api/search?q={source_name}", headers=headers)
        self.assertEqual(r.status_code, 200, r.text)

        results = r.json()["results"]
        source_hits = [item for item in results if item["type"] == "source"]
        self.assertEqual(len(source_hits), 1, results)

        hit = source_hits[0]
        self.assertEqual(hit["id"], source_id)
        self.assertEqual(hit["label"], source_name)
        self.assertEqual(hit["url"], f"/ecosystem?sourceId={source_id}")
        self.assertIn("Source", hit["subtitle"])
        self.assertIn("dataset", hit["subtitle"])

    def test_search_surfaces_all_three_tiers_for_one_query(self):
        headers = self._register_and_login(f"src2{self._n}@a.com", f"Source Search Org 2 {self._n}")

        tag = f"warehouse{self._n}"
        # Source name, dataset name, and column name all mention the
        # same tag, so a single query is a genuine three-way match -
        # the old flat top-K could easily let one type win and starve
        # the others out at a small limit.
        # Hyphens, not underscores, on purpose: TF-IDF's default
        # tokenizer treats underscore as a word character, so
        # "tag_orders" would tokenize as one single compound token
        # that never matches a query for "tag" alone. A hyphen is an
        # actual token boundary, giving "tag" and "orders" as separate
        # vocabulary terms - closer to how a real multi-word table/
        # column name would tokenize anyway.
        scan_with_tag = {
            "datasets": [{
                "schema_name": "public",
                "table_name": f"{tag}-orders",
                "columns": [("id", "integer", "NO"), (f"{tag}-status", "text", "YES")],
                "row_count": 1,
                "column_stats": {
                    "id": {"non_null": 1, "distinct": 1},
                    f"{tag}-status": {"non_null": 1, "distinct": 1},
                },
                "column_samples": {"id": ["1"], f"{tag}-status": ["active"]},
            }],
            "foreign_keys": [],
        }
        self._create_and_scan_source(headers, f"{tag} System", scan_with_tag)

        r = self.client.get(f"/api/search?q={tag}&limit=3", headers=headers)
        self.assertEqual(r.status_code, 200, r.text)

        results = r.json()["results"]
        types_present = {item["type"] for item in results}

        self.assertIn("source", types_present)
        self.assertIn("dataset", types_present)
        self.assertIn("column", types_present)

    def test_source_search_is_tenant_scoped(self):
        headers_a = self._register_and_login(f"src3a{self._n}@a.com", f"Source Search Org 3a {self._n}")
        headers_b = self._register_and_login(f"src3b{self._n}@a.com", f"Source Search Org 3b {self._n}")

        source_name = f"CrossTenantSource{self._n}"
        self._create_and_scan_source(headers_a, source_name, SCAN_RESULT)

        r = self.client.get(f"/api/search?q={source_name}", headers=headers_b)
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["results"], [])


if __name__ == "__main__":
    unittest.main()
