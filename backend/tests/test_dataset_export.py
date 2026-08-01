"""
Integration tests for GET /api/datasets/{id}/export - the per-dataset
CSV download that didn't exist anywhere before (the only prior
"download" capability in the product was the org-wide compliance PDF).
Covers: correct headers/content type, dataset-level fields repeated on
every column row, a graceful single-row output for a dataset with no
profiled columns, and tenant scoping.
"""

import csv
import io
import unittest
import uuid

from fastapi.testclient import TestClient

from app.main import app


class DatasetExportTests(unittest.TestCase):

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

    def _upload_dataset(self, headers, table_name="customers"):
        csv_bytes = b"customer_id,email\n1,a@b.com\n2,c@d.com\n"
        r = self.client.post(
            "/api/sources/upload",
            headers=headers,
            data={"name": f"src-{table_name}-{self._n}", "table_name": table_name, "schema_name": "public"},
            files={"file": (f"{table_name}.csv", csv_bytes, "text/csv")},
        )
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()["dataset_id"]

    def test_export_returns_csv_with_one_row_per_column(self):
        headers = self._register_and_login(f"dexp1{self._n}@a.com", f"Export Org 1 {self._n}")
        dataset_id = self._upload_dataset(headers)

        r = self.client.get(f"/api/datasets/{dataset_id}/export", headers=headers)
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.headers["content-type"].split(";")[0], "text/csv")
        self.assertIn("attachment", r.headers["content-disposition"])
        self.assertIn("public.customers", r.headers["content-disposition"])

        rows = list(csv.reader(io.StringIO(r.text)))
        header, data_rows = rows[0], rows[1:]

        self.assertEqual(header[0:2], ["schema_name", "dataset_name"])
        self.assertIn("column_name", header)
        self.assertIn("data_type", header)

        # customer_id + email = 2 profiled columns, so 2 data rows.
        self.assertEqual(len(data_rows), 2)

        schema_col = header.index("schema_name")
        dataset_col = header.index("dataset_name")
        column_col = header.index("column_name")

        for row in data_rows:
            self.assertEqual(row[schema_col], "public")
            self.assertEqual(row[dataset_col], "customers")

        column_names = {row[column_col] for row in data_rows}
        self.assertEqual(column_names, {"customer_id", "email"})

    def test_export_is_tenant_scoped(self):
        headers_a = self._register_and_login(f"dexp2a{self._n}@a.com", f"Export Org 2A {self._n}")
        headers_b = self._register_and_login(f"dexp2b{self._n}@a.com", f"Export Org 2B {self._n}")

        dataset_id = self._upload_dataset(headers_a)

        r = self.client.get(f"/api/datasets/{dataset_id}/export", headers=headers_b)
        self.assertEqual(r.status_code, 404)

    def test_export_requires_auth(self):
        r = self.client.get(f"/api/datasets/{uuid.uuid4()}/export")
        self.assertEqual(r.status_code, 401)


if __name__ == "__main__":
    unittest.main()
