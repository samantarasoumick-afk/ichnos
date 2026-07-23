"""
Integration tests for POST /api/sources/upload/dbt: uploads a real
multipart manifest.json (+ optional catalog.json) and verifies models
become datasets, the depends_on graph becomes AUTO lineage edges
carrying the compiled SQL as transformation_description, dbt's own
model descriptions win over the auto-generated fallback, tenant
scoping holds, and non-model nodes (tests) are skipped.
"""

import json
import unittest
import uuid

from fastapi.testclient import TestClient

from app.main import app


PROJECT = "my_project"


def _manifest():
    return {
        "nodes": {
            f"model.{PROJECT}.raw_orders": {
                "resource_type": "model",
                "name": "raw_orders",
                "alias": "raw_orders",
                "schema": "analytics",
                "description": "Raw orders from the source system.",
                "columns": {
                    "order_id": {"name": "order_id"},
                    "customer_id": {"name": "customer_id"},
                },
                "depends_on": {"nodes": []},
                "compiled_code": "select * from raw.orders",
            },
            f"model.{PROJECT}.stg_orders": {
                "resource_type": "model",
                "name": "stg_orders",
                "alias": "stg_orders",
                "schema": "analytics",
                "description": "Deduplicated, staged orders.",
                "columns": {
                    "order_id": {"name": "order_id"},
                    "customer_id": {"name": "customer_id"},
                    "total_amount": {"name": "total_amount"},
                },
                "depends_on": {"nodes": [f"model.{PROJECT}.raw_orders"]},
                "compiled_code": (
                    "select order_id, customer_id, total_amount "
                    "from analytics.raw_orders"
                ),
            },
            # A test node depending on stg_orders - must be skipped
            # entirely (not a dataset, and depends_on edges pointing
            # *from* it are irrelevant since it never appears as an
            # upstream/downstream dataset).
            f"test.{PROJECT}.not_null_stg_orders_order_id": {
                "resource_type": "test",
                "name": "not_null_stg_orders_order_id",
                "depends_on": {"nodes": [f"model.{PROJECT}.stg_orders"]},
            },
        }
    }


def _catalog():
    return {
        "nodes": {
            f"model.{PROJECT}.raw_orders": {
                "columns": {
                    "order_id": {"name": "order_id", "type": "INTEGER", "index": 1},
                    "customer_id": {"name": "customer_id", "type": "INTEGER", "index": 2},
                },
                "stats": {"row_count": {"value": 100}},
            },
            f"model.{PROJECT}.stg_orders": {
                "columns": {
                    "order_id": {"name": "order_id", "type": "INTEGER", "index": 1},
                    "customer_id": {"name": "customer_id", "type": "INTEGER", "index": 2},
                    "total_amount": {"name": "total_amount", "type": "NUMERIC", "index": 3},
                },
                "stats": {"row_count": {"value": 95}},
            },
        }
    }


class DbtUploadEndpointTests(unittest.TestCase):

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

    def _upload(self, headers, name, manifest=None, catalog=None, manifest_filename="manifest.json"):
        files = {
            "manifest_file": (
                manifest_filename,
                json.dumps(manifest if manifest is not None else _manifest()),
                "application/json",
            ),
        }
        if catalog is not None:
            files["catalog_file"] = ("catalog.json", json.dumps(catalog), "application/json")

        return self.client.post(
            "/api/sources/upload/dbt",
            headers=headers,
            data={"name": name},
            files=files,
        )

    def test_successful_upload_creates_datasets_and_lineage(self):
        headers = self._register_and_login(f"dbt1{self._n}@a.com", f"Dbt Org 1 {self._n}")

        r = self._upload(headers, f"dbt Project {self._n}", catalog=_catalog())
        self.assertEqual(r.status_code, 200, r.text)
        body = r.json()
        self.assertEqual(body["datasets_discovered"], 2)
        self.assertEqual(body["lineage_edges_created"], 1)

        r = self.client.get("/api/sources", headers=headers)
        self.assertEqual(r.json()[0]["type"], "dbt")

        r = self.client.get("/api/datasets", headers=headers)
        datasets = r.json()
        self.assertEqual(len(datasets), 2)
        by_name = {d["name"]: d for d in datasets}
        self.assertIn("raw_orders", by_name)
        self.assertIn("stg_orders", by_name)
        self.assertEqual(by_name["raw_orders"]["schema_name"], "analytics")
        # dbt's own description wins over the auto-generated fallback.
        self.assertEqual(
            by_name["stg_orders"]["description"],
            "Deduplicated, staged orders.",
        )

        raw_id = by_name["raw_orders"]["id"]
        stg_id = by_name["stg_orders"]["id"]

        r = self.client.get(f"/api/columns/dataset/{stg_id}", headers=headers)
        columns_by_name = {c["name"]: c for c in r.json()}
        self.assertEqual(columns_by_name["total_amount"]["data_type"], "NUMERIC")

        r = self.client.get("/api/lineage", headers=headers)
        edges = r.json()
        self.assertEqual(len(edges), 1)
        edge = edges[0]
        self.assertEqual(edge["upstream_dataset_id"], raw_id)
        self.assertEqual(edge["downstream_dataset_id"], stg_id)
        self.assertEqual(edge["transformation_type"], "dbt_model")
        self.assertEqual(edge["documentation_source"], "AUTO")
        self.assertIn("analytics.raw_orders", edge["transformation_description"])

    def test_manifest_only_upload_uses_unknown_column_types(self):
        headers = self._register_and_login(f"dbt2{self._n}@a.com", f"Dbt Org 2 {self._n}")

        r = self._upload(headers, f"dbt No Catalog {self._n}")
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["datasets_discovered"], 2)

        r = self.client.get("/api/datasets", headers=headers)
        raw_id = next(d["id"] for d in r.json() if d["name"] == "raw_orders")

        r = self.client.get(f"/api/columns/dataset/{raw_id}", headers=headers)
        columns_by_name = {c["name"]: c for c in r.json()}
        self.assertEqual(columns_by_name["order_id"]["data_type"], "unknown")

    def test_test_nodes_are_not_ingested_as_datasets(self):
        headers = self._register_and_login(f"dbt3{self._n}@a.com", f"Dbt Org 3 {self._n}")

        r = self._upload(headers, f"dbt Test Filter {self._n}", catalog=_catalog())
        self.assertEqual(r.status_code, 200, r.text)

        r = self.client.get("/api/datasets", headers=headers)
        names = {d["name"] for d in r.json()}
        self.assertNotIn("not_null_stg_orders_order_id", names)

    def test_manifest_missing_nodes_key_rejected(self):
        headers = self._register_and_login(f"dbt4{self._n}@a.com", f"Dbt Org 4 {self._n}")

        r = self._upload(headers, f"Bad Manifest {self._n}", manifest={"not_nodes": {}})
        self.assertEqual(r.status_code, 400)

    def test_malformed_json_rejected(self):
        headers = self._register_and_login(f"dbt5{self._n}@a.com", f"Dbt Org 5 {self._n}")

        r = self.client.post(
            "/api/sources/upload/dbt",
            headers=headers,
            data={"name": f"Malformed {self._n}"},
            files={"manifest_file": ("manifest.json", "{not valid json", "application/json")},
        )
        self.assertEqual(r.status_code, 400)

    def test_non_json_manifest_extension_rejected(self):
        headers = self._register_and_login(f"dbt6{self._n}@a.com", f"Dbt Org 6 {self._n}")

        r = self._upload(headers, f"Bad Ext {self._n}", manifest_filename="manifest.txt")
        self.assertEqual(r.status_code, 400)

    def test_duplicate_source_name_rejected(self):
        headers = self._register_and_login(f"dbt7{self._n}@a.com", f"Dbt Org 7 {self._n}")

        source_name = f"Dup dbt {self._n}"
        r = self._upload(headers, source_name)
        self.assertEqual(r.status_code, 200, r.text)

        r = self._upload(headers, source_name)
        self.assertEqual(r.status_code, 400)

    def test_upload_logs_audit_event(self):
        headers = self._register_and_login(f"dbt8{self._n}@a.com", f"Dbt Org 8 {self._n}")

        r = self._upload(headers, f"dbt Audit {self._n}")
        self.assertEqual(r.status_code, 200, r.text)

        r = self.client.get("/api/audit-log", headers=headers)
        actions = [entry["action"] for entry in r.json()]
        self.assertIn("source.upload_dbt", actions)

    def test_tenant_scoping(self):
        headers_a = self._register_and_login(f"dbt9a{self._n}@a.com", f"Dbt Org 9a {self._n}")
        headers_b = self._register_and_login(f"dbt9b{self._n}@a.com", f"Dbt Org 9b {self._n}")

        r = self._upload(headers_a, f"Tenant A dbt {self._n}")
        self.assertEqual(r.status_code, 200, r.text)

        r = self.client.get("/api/datasets", headers=headers_b)
        self.assertEqual(r.json(), [])

        r = self.client.get("/api/lineage", headers=headers_b)
        self.assertEqual(r.json(), [])

    def test_upload_requires_admin_or_steward_role(self):
        headers = self._register_and_login(f"dbt10{self._n}@a.com", f"Dbt Org 10 {self._n}")

        r = self.client.post("/api/users", headers=headers, json={
            "email": f"dbtviewer{self._n}@a.com",
            "password": "password123",
            "role": "viewer",
        })
        self.assertEqual(r.status_code, 200, r.text)

        r = self.client.post("/api/auth/login", json={
            "email": f"dbtviewer{self._n}@a.com",
            "password": "password123",
        })
        viewer_headers = {"Authorization": f"Bearer {r.json()['access_token']}"}

        r = self._upload(viewer_headers, f"Viewer dbt {self._n}")
        self.assertEqual(r.status_code, 403)


if __name__ == "__main__":
    unittest.main()
