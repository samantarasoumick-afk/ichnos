"""
Tests for lineage transformation/filter documentation: manually-
created edges carry documentation_source="MANUAL" and the free-text
transformation_description/filter_logic fields, discovery-created
edges are "AUTO", editing an edge afterward (e.g. to document what an
auto-discovered FK join actually filters) flips it to MANUAL, and
everything is tenant-scoped and role-gated.
"""

import unittest
import uuid
from unittest.mock import patch, MagicMock

from fastapi.testclient import TestClient

from app.db.database import SessionLocal
from app.main import app
from app.models.dataset import Dataset
from app.models.user import User


class LineageDocumentationTests(unittest.TestCase):

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

    def _create_two_datasets(self, headers, email):
        db = SessionLocal()
        try:
            me = db.query(User).filter(User.email == email).first()

            r = self.client.post("/api/sources", headers=headers, json={
                "name": f"Source {self._n}",
                "type": "postgresql",
                "connection_config": {"host": "x"},
            })
            source_id = r.json()["id"]

            upstream = Dataset(
                name="raw_orders", schema_name="public",
                source_id=source_id, organization_id=me.organization_id,
            )
            downstream = Dataset(
                name="clean_orders", schema_name="public",
                source_id=source_id, organization_id=me.organization_id,
            )
            db.add_all([upstream, downstream])
            db.commit()
            db.refresh(upstream)
            db.refresh(downstream)
            return upstream.id, downstream.id
        finally:
            db.close()

    def test_manually_created_edge_carries_documentation(self):
        headers = self._register_and_login(f"ld1{self._n}@a.com", f"LineageDoc Org 1 {self._n}")
        upstream_id, downstream_id = self._create_two_datasets(headers, f"ld1{self._n}@a.com")

        r = self.client.post("/api/lineage", headers=headers, json={
            "upstream_dataset_id": upstream_id,
            "downstream_dataset_id": downstream_id,
            "transformation_type": "dbt_model",
            "transformation_description": "Dedupes raw_orders on order_id, keeping the latest row.",
            "filter_logic": "WHERE status != 'test_order'",
        })
        self.assertEqual(r.status_code, 200, r.text)
        body = r.json()
        self.assertEqual(body["documentation_source"], "MANUAL")
        self.assertIn("Dedupes", body["transformation_description"])
        self.assertIn("test_order", body["filter_logic"])

    def test_discovery_created_edge_is_auto(self):
        headers = self._register_and_login(f"ld2{self._n}@a.com", f"LineageDoc Org 2 {self._n}")

        r = self.client.post("/api/sources", headers=headers, json={
            "name": f"Source2 {self._n}",
            "type": "postgresql",
            "connection_config": {"host": "x", "database": "y", "user": "z", "password": "p"},
        })
        source_id = r.json()["id"]

        scan_result = {
            "datasets": [
                {
                    "schema_name": "public", "table_name": "orders",
                    "columns": [("id", "integer", "NO"), ("customer_id", "integer", "YES")],
                    "row_count": 1,
                    "column_stats": {"id": {"non_null": 1, "distinct": 1}, "customer_id": {"non_null": 1, "distinct": 1}},
                    "column_samples": {"id": ["1"], "customer_id": ["1"]},
                },
                {
                    "schema_name": "public", "table_name": "customers",
                    "columns": [("id", "integer", "NO")],
                    "row_count": 1,
                    "column_stats": {"id": {"non_null": 1, "distinct": 1}},
                    "column_samples": {"id": ["1"]},
                },
            ],
            "foreign_keys": [
                ("public", "orders", "customer_id", "public", "customers", "id"),
            ],
        }

        with patch("app.api.scanner.get_scanner") as mock_get_scanner:
            mock_get_scanner.return_value = MagicMock(return_value=scan_result)
            r = self.client.post(f"/api/scanner/{source_id}", headers=headers)
            self.assertEqual(r.status_code, 200, r.text)

        r = self.client.get("/api/lineage", headers=headers)
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(len(r.json()), 1)
        self.assertEqual(r.json()[0]["documentation_source"], "AUTO")
        self.assertEqual(r.json()[0]["transformation_type"], "FOREIGN_KEY")

    def test_discovery_does_not_cross_link_datasets_across_tenants(self):
        """
        Regression test: LineageDiscoveryService.discover() used to
        look up upstream/downstream datasets by schema/table name with
        no organization filter, so two tenants both having a
        "public.customers" table (an extremely common name) could get
        a lineage edge silently attached to the wrong tenant's
        dataset. Both orgs below use identical table names on purpose.
        """

        headers_a = self._register_and_login(f"ld7a{self._n}@a.com", f"LineageDoc Org 7a {self._n}")
        headers_b = self._register_and_login(f"ld7b{self._n}@a.com", f"LineageDoc Org 7b {self._n}")

        scan_result = {
            "datasets": [
                {
                    "schema_name": "public", "table_name": "orders",
                    "columns": [("id", "integer", "NO"), ("customer_id", "integer", "YES")],
                    "row_count": 1,
                    "column_stats": {"id": {"non_null": 1, "distinct": 1}, "customer_id": {"non_null": 1, "distinct": 1}},
                    "column_samples": {"id": ["1"], "customer_id": ["1"]},
                },
                {
                    "schema_name": "public", "table_name": "customers",
                    "columns": [("id", "integer", "NO")],
                    "row_count": 1,
                    "column_stats": {"id": {"non_null": 1, "distinct": 1}},
                    "column_samples": {"id": ["1"]},
                },
            ],
            "foreign_keys": [
                ("public", "orders", "customer_id", "public", "customers", "id"),
            ],
        }

        # Org A scans first and gets its own orders/customers pair.
        r = self.client.post("/api/sources", headers=headers_a, json={
            "name": f"SourceA {self._n}", "type": "postgresql",
            "connection_config": {"host": "x", "database": "y", "user": "z", "password": "p"},
        })
        source_a_id = r.json()["id"]

        with patch("app.api.scanner.get_scanner") as mock_get_scanner:
            mock_get_scanner.return_value = MagicMock(return_value=scan_result)
            r = self.client.post(f"/api/scanner/{source_a_id}", headers=headers_a)
            self.assertEqual(r.status_code, 200, r.text)

        # Org B scans an identically-named orders/customers pair.
        r = self.client.post("/api/sources", headers=headers_b, json={
            "name": f"SourceB {self._n}", "type": "postgresql",
            "connection_config": {"host": "x", "database": "y", "user": "z", "password": "p"},
        })
        source_b_id = r.json()["id"]

        with patch("app.api.scanner.get_scanner") as mock_get_scanner:
            mock_get_scanner.return_value = MagicMock(return_value=scan_result)
            r = self.client.post(f"/api/scanner/{source_b_id}", headers=headers_b)
            self.assertEqual(r.status_code, 200, r.text)

        datasets_a = self.client.get("/api/datasets", headers=headers_a).json()
        datasets_b = self.client.get("/api/datasets", headers=headers_b).json()
        ids_a = {d["id"] for d in datasets_a}
        ids_b = {d["id"] for d in datasets_b}

        lineage_a = self.client.get("/api/lineage", headers=headers_a).json()
        lineage_b = self.client.get("/api/lineage", headers=headers_b).json()

        self.assertEqual(len(lineage_a), 1)
        self.assertEqual(len(lineage_b), 1)

        # Each org's edge must point at its own datasets only, never
        # the other org's identically-named ones.
        self.assertIn(lineage_a[0]["upstream_dataset_id"], ids_a)
        self.assertIn(lineage_a[0]["downstream_dataset_id"], ids_a)
        self.assertNotIn(lineage_a[0]["upstream_dataset_id"], ids_b)
        self.assertNotIn(lineage_a[0]["downstream_dataset_id"], ids_b)

        self.assertIn(lineage_b[0]["upstream_dataset_id"], ids_b)
        self.assertIn(lineage_b[0]["downstream_dataset_id"], ids_b)

    def test_updating_an_edge_documents_it_and_flips_to_manual(self):
        headers = self._register_and_login(f"ld3{self._n}@a.com", f"LineageDoc Org 3 {self._n}")
        upstream_id, downstream_id = self._create_two_datasets(headers, f"ld3{self._n}@a.com")

        r = self.client.post("/api/lineage", headers=headers, json={
            "upstream_dataset_id": upstream_id,
            "downstream_dataset_id": downstream_id,
        })
        edge_id = r.json()["id"]

        r = self.client.patch(f"/api/lineage/{edge_id}", headers=headers, json={
            "transformation_description": "Adds a computed total_amount column.",
        })
        self.assertEqual(r.status_code, 200, r.text)
        self.assertIn("total_amount", r.json()["transformation_description"])
        self.assertEqual(r.json()["documentation_source"], "MANUAL")

    def test_update_requires_admin_or_steward(self):
        headers = self._register_and_login(f"ld4{self._n}@a.com", f"LineageDoc Org 4 {self._n}")
        upstream_id, downstream_id = self._create_two_datasets(headers, f"ld4{self._n}@a.com")

        r = self.client.post("/api/lineage", headers=headers, json={
            "upstream_dataset_id": upstream_id,
            "downstream_dataset_id": downstream_id,
        })
        edge_id = r.json()["id"]

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

        r = self.client.patch(f"/api/lineage/{edge_id}", headers=viewer_headers, json={
            "transformation_description": "nope",
        })
        self.assertEqual(r.status_code, 403)

    def test_update_is_tenant_scoped(self):
        headers_a = self._register_and_login(f"ld5a{self._n}@a.com", f"LineageDoc Org 5a {self._n}")
        headers_b = self._register_and_login(f"ld5b{self._n}@a.com", f"LineageDoc Org 5b {self._n}")
        upstream_id, downstream_id = self._create_two_datasets(headers_a, f"ld5a{self._n}@a.com")

        r = self.client.post("/api/lineage", headers=headers_a, json={
            "upstream_dataset_id": upstream_id,
            "downstream_dataset_id": downstream_id,
        })
        edge_id = r.json()["id"]

        r = self.client.patch(f"/api/lineage/{edge_id}", headers=headers_b, json={
            "transformation_description": "shouldn't work",
        })
        self.assertEqual(r.status_code, 404)

    def test_lineage_create_and_update_are_audit_logged(self):
        headers = self._register_and_login(f"ld6{self._n}@a.com", f"LineageDoc Org 6 {self._n}")
        upstream_id, downstream_id = self._create_two_datasets(headers, f"ld6{self._n}@a.com")

        r = self.client.post("/api/lineage", headers=headers, json={
            "upstream_dataset_id": upstream_id,
            "downstream_dataset_id": downstream_id,
        })
        edge_id = r.json()["id"]

        self.client.patch(f"/api/lineage/{edge_id}", headers=headers, json={
            "filter_logic": "WHERE amount > 0",
        })

        r = self.client.get("/api/audit-log", headers=headers)
        actions = [entry["action"] for entry in r.json()]
        self.assertIn("lineage.create", actions)
        self.assertIn("lineage.update", actions)


if __name__ == "__main__":
    unittest.main()
