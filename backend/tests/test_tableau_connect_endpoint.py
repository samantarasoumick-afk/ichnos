"""
Integration tests for POST /api/sources/connect/tableau. Mocks
fetch_workbooks_with_upstream_tables (the network boundary - there's
no live Tableau server here) at the point sources.py imports it, and
verifies workbooks become pseudo-Datasets, upstream tables become AUTO
lineage edges against already-cataloged datasets, tenant scoping
holds, and connection failures surface as a 400 rather than a 500.
"""

import unittest
import uuid
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.connectors.tableau_connector import TableauConnectionError
from app.main import app


def _workbook(luid, name, project_name, upstream_tables):
    return {
        "luid": luid,
        "name": name,
        "project_name": project_name,
        "upstream_tables": upstream_tables,
    }


class TableauConnectEndpointTests(unittest.TestCase):

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

    def _connect(self, headers, name, site_content_url="acme"):
        return self.client.post(
            "/api/sources/connect/tableau",
            headers=headers,
            json={
                "name": name,
                "server_url": "https://tableau.example.com",
                "site_content_url": site_content_url,
                "token_name": "my-pat",
                "token_value": "secret-value",
            },
        )

    def _create_live_source_table(self, headers, schema_name, table_name):
        """
        Creates a real cataloged Dataset via the CSV upload path (the
        cheapest way to get an existing Dataset in place to test
        lineage matching against) so a workbook's upstreamTables entry
        has something real to match onto.
        """
        csv_bytes = b"id,email\n1,a@b.com\n"
        r = self.client.post(
            "/api/sources/upload",
            headers=headers,
            data={"name": f"src-{table_name}-{self._n}", "table_name": table_name, "schema_name": schema_name},
            files={"file": (f"{table_name}.csv", csv_bytes, "text/csv")},
        )
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()["dataset_id"]

    @patch("app.api.sources.fetch_workbooks_with_upstream_tables")
    def test_successful_connect_creates_datasets_and_lineage(self, mock_fetch):
        headers = self._register_and_login(f"tab1{self._n}@a.com", f"Tab Org 1 {self._n}")

        orders_id = self._create_live_source_table(headers, "public", "orders")

        mock_fetch.return_value = [
            _workbook(
                "wb-1", "Sales Overview", "Finance",
                [{"name": "orders", "schema": "public"}],
            ),
        ]

        r = self._connect(headers, f"Tableau Site {self._n}")
        self.assertEqual(r.status_code, 200, r.text)
        body = r.json()
        self.assertEqual(body["workbooks_discovered"], 1)
        self.assertEqual(body["lineage_edges_created"], 1)

        r = self.client.get("/api/sources", headers=headers)
        types = [s["type"] for s in r.json()]
        self.assertIn("tableau", types)

        r = self.client.get("/api/datasets", headers=headers)
        by_name = {d["name"]: d for d in r.json()}
        self.assertIn("Sales Overview", by_name)
        self.assertEqual(by_name["Sales Overview"]["schema_name"], "Finance")

        wb_id = by_name["Sales Overview"]["id"]

        r = self.client.get("/api/lineage", headers=headers)
        edges = r.json()
        edge = next(e for e in edges if e["downstream_dataset_id"] == wb_id)
        self.assertEqual(edge["upstream_dataset_id"], orders_id)
        self.assertEqual(edge["transformation_type"], "TABLEAU_WORKBOOK")
        self.assertEqual(edge["documentation_source"], "AUTO")

    @patch("app.api.sources.fetch_workbooks_with_upstream_tables")
    def test_workbook_with_no_matching_upstream_table_still_ingests(self, mock_fetch):
        headers = self._register_and_login(f"tab2{self._n}@a.com", f"Tab Org 2 {self._n}")

        mock_fetch.return_value = [
            _workbook("wb-1", "Orphan Report", None, [{"name": "nobody_has_this", "schema": "public"}]),
        ]

        r = self._connect(headers, f"Tableau Orphan {self._n}")
        self.assertEqual(r.status_code, 200, r.text)
        body = r.json()
        self.assertEqual(body["workbooks_discovered"], 1)
        self.assertEqual(body["lineage_edges_created"], 0)

        r = self.client.get("/api/datasets", headers=headers)
        names = {d["name"] for d in r.json()}
        self.assertIn("Orphan Report", names)

    @patch("app.api.sources.fetch_workbooks_with_upstream_tables")
    def test_connection_failure_returns_400_not_500(self, mock_fetch):
        headers = self._register_and_login(f"tab3{self._n}@a.com", f"Tab Org 3 {self._n}")

        mock_fetch.side_effect = TableauConnectionError("Tableau sign-in failed (401): bad token")

        r = self._connect(headers, f"Tableau Bad {self._n}")
        self.assertEqual(r.status_code, 400)
        self.assertIn("bad token", r.json()["detail"])

        # A failed connect shouldn't leave a half-created source behind.
        r = self.client.get("/api/sources", headers=headers)
        self.assertEqual(r.json(), [])

    @patch("app.api.sources.fetch_workbooks_with_upstream_tables")
    def test_duplicate_source_name_rejected(self, mock_fetch):
        headers = self._register_and_login(f"tab4{self._n}@a.com", f"Tab Org 4 {self._n}")
        mock_fetch.return_value = []

        source_name = f"Dup Tableau {self._n}"
        r = self._connect(headers, source_name)
        self.assertEqual(r.status_code, 200, r.text)

        r = self._connect(headers, source_name)
        self.assertEqual(r.status_code, 400)

    @patch("app.api.sources.fetch_workbooks_with_upstream_tables")
    def test_upload_logs_audit_event(self, mock_fetch):
        headers = self._register_and_login(f"tab5{self._n}@a.com", f"Tab Org 5 {self._n}")
        mock_fetch.return_value = []

        r = self._connect(headers, f"Tableau Audit {self._n}")
        self.assertEqual(r.status_code, 200, r.text)

        r = self.client.get("/api/audit-log", headers=headers)
        actions = [entry["action"] for entry in r.json()]
        self.assertIn("source.connect_tableau", actions)

    @patch("app.api.sources.fetch_workbooks_with_upstream_tables")
    def test_tenant_scoping(self, mock_fetch):
        headers_a = self._register_and_login(f"tab6a{self._n}@a.com", f"Tab Org 6a {self._n}")
        headers_b = self._register_and_login(f"tab6b{self._n}@a.com", f"Tab Org 6b {self._n}")

        orders_id = self._create_live_source_table(headers_a, "public", "orders")

        mock_fetch.return_value = [
            _workbook("wb-1", "Cross Tenant Report", None, [{"name": "orders", "schema": "public"}]),
        ]

        r = self._connect(headers_a, f"Tenant A Tableau {self._n}")
        self.assertEqual(r.status_code, 200, r.text)

        # Org B never sees org A's workbook dataset or the lineage
        # edge pointing at org A's "orders" table, even though the
        # workbook's upstream table name/schema would otherwise match.
        r = self.client.get("/api/datasets", headers=headers_b)
        self.assertEqual(r.json(), [])

        r = self.client.get("/api/lineage", headers=headers_b)
        self.assertEqual(r.json(), [])

        del orders_id  # only needed to seed org A's catalog above

    @patch("app.api.sources.fetch_workbooks_with_upstream_tables")
    def test_connect_requires_admin_or_steward_role(self, mock_fetch):
        headers = self._register_and_login(f"tab7{self._n}@a.com", f"Tab Org 7 {self._n}")
        mock_fetch.return_value = []

        r = self.client.post("/api/users", headers=headers, json={
            "email": f"tabviewer{self._n}@a.com",
            "password": "password123",
            "role": "viewer",
        })
        self.assertEqual(r.status_code, 200, r.text)

        r = self.client.post("/api/auth/login", json={
            "email": f"tabviewer{self._n}@a.com",
            "password": "password123",
        })
        viewer_headers = {"Authorization": f"Bearer {r.json()['access_token']}"}

        r = self._connect(viewer_headers, f"Viewer Tableau {self._n}")
        self.assertEqual(r.status_code, 403)


if __name__ == "__main__":
    unittest.main()
