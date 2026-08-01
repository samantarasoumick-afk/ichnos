"""
Integration tests for GET /api/dashboard/overview - in particular the
new `total_sources` field (previously the only place a source count
existed anywhere was the internal platform-admin console, not the
catalog-facing dashboard a regular user actually sees).
"""

import unittest
import uuid

from fastapi.testclient import TestClient

from app.main import app


class DashboardOverviewTests(unittest.TestCase):

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

    def _upload_source(self, headers, table_name):
        csv_bytes = b"id,value\n1,10\n2,20\n"
        r = self.client.post(
            "/api/sources/upload",
            headers=headers,
            data={"name": f"src-{table_name}-{self._n}", "table_name": table_name, "schema_name": "public"},
            files={"file": (f"{table_name}.csv", csv_bytes, "text/csv")},
        )
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()

    def test_total_sources_reflects_uploaded_sources(self):
        headers = self._register_and_login(f"dash1{self._n}@a.com", f"Dash Org 1 {self._n}")

        r = self.client.get("/api/dashboard/overview", headers=headers)
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["total_sources"], 0)

        self._upload_source(headers, "orders")
        self._upload_source(headers, "customers")

        r = self.client.get("/api/dashboard/overview", headers=headers)
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["total_sources"], 2)

    def test_total_sources_is_tenant_scoped(self):
        headers_a = self._register_and_login(f"dash2a{self._n}@a.com", f"Dash Org 2A {self._n}")
        headers_b = self._register_and_login(f"dash2b{self._n}@a.com", f"Dash Org 2B {self._n}")

        self._upload_source(headers_a, "orders")
        self._upload_source(headers_a, "customers")
        self._upload_source(headers_b, "orders")

        r = self.client.get("/api/dashboard/overview", headers=headers_a)
        self.assertEqual(r.json()["total_sources"], 2)

        r = self.client.get("/api/dashboard/overview", headers=headers_b)
        self.assertEqual(r.json()["total_sources"], 1)


if __name__ == "__main__":
    unittest.main()
