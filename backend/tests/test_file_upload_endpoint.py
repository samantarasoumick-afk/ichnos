"""
Integration tests for POST /api/sources/upload: uploads a real
multipart CSV body and verifies it flows through the exact same
ingestion pipeline a live scan uses - source/dataset/columns created,
PII classified by the real privacy engine, data quality profiled,
an audit event logged, and one org can't see another org's upload.
"""

import unittest
import uuid

from fastapi.testclient import TestClient

from app.main import app


CSV_BODY = (
    b"id,email,notes\n"
    b"1,alice@example.com,first row\n"
    b"2,bob@example.com,second row\n"
    b"3,carol@example.com,third row\n"
)


class FileUploadEndpointTests(unittest.TestCase):

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

    def _upload(self, headers, name, table_name, body=CSV_BODY, filename="people.csv", schema_name=None):
        data = {"name": name, "table_name": table_name}
        if schema_name is not None:
            data["schema_name"] = schema_name
        return self.client.post(
            "/api/sources/upload",
            headers=headers,
            data=data,
            files={"file": (filename, body, "text/csv")},
        )

    def test_successful_upload_creates_source_dataset_and_classifies_columns(self):
        headers = self._register_and_login(f"upl{self._n}@a.com", f"Upload Org {self._n}")

        r = self._upload(headers, f"CSV Source {self._n}", "people")
        self.assertEqual(r.status_code, 200, r.text)
        body = r.json()
        self.assertIn("source_id", body)
        self.assertIn("dataset_id", body)

        r = self.client.get("/api/sources", headers=headers)
        sources = r.json()
        self.assertEqual(len(sources), 1)
        self.assertEqual(sources[0]["type"], "file_upload")

        r = self.client.get("/api/datasets", headers=headers)
        datasets = r.json()
        self.assertEqual(len(datasets), 1)
        self.assertEqual(datasets[0]["name"], "people")
        self.assertEqual(datasets[0]["schema_name"], "uploads")

        r = self.client.get(f"/api/columns/dataset/{body['dataset_id']}", headers=headers)
        self.assertEqual(r.status_code, 200, r.text)
        columns_by_name = {c["name"]: c for c in r.json()}
        self.assertEqual(set(columns_by_name), {"id", "email", "notes"})
        self.assertEqual(columns_by_name["email"]["classification"], "PII")

    def test_upload_creates_data_quality_profile(self):
        headers = self._register_and_login(f"dq{self._n}@a.com", f"DQ Org {self._n}")

        r = self._upload(headers, f"CSV Source DQ {self._n}", "people_dq")
        self.assertEqual(r.status_code, 200, r.text)
        dataset_id = r.json()["dataset_id"]

        r = self.client.get(f"/api/data-quality/dataset/{dataset_id}", headers=headers)
        self.assertEqual(r.status_code, 200, r.text)
        self.assertIn("overall_score", r.json())

    def test_upload_logs_audit_event(self):
        headers = self._register_and_login(f"aud{self._n}@a.com", f"Audit Org {self._n}")

        r = self._upload(headers, f"CSV Source Audit {self._n}", "people_audit")
        self.assertEqual(r.status_code, 200, r.text)

        r = self.client.get("/api/audit-log", headers=headers)
        self.assertEqual(r.status_code, 200, r.text)
        actions = [entry["action"] for entry in r.json()]
        self.assertIn("source.upload", actions)

    def test_duplicate_source_name_rejected(self):
        headers = self._register_and_login(f"dup{self._n}@a.com", f"Dup Org {self._n}")

        source_name = f"Dup CSV {self._n}"
        r = self._upload(headers, source_name, "people_a")
        self.assertEqual(r.status_code, 200, r.text)

        r = self._upload(headers, source_name, "people_b")
        self.assertEqual(r.status_code, 400)

    def test_non_csv_extension_rejected(self):
        headers = self._register_and_login(f"ext{self._n}@a.com", f"Ext Org {self._n}")

        r = self._upload(headers, f"Bad Ext {self._n}", "people", filename="people.txt")
        self.assertEqual(r.status_code, 400)

    def test_oversized_file_rejected(self):
        headers = self._register_and_login(f"big{self._n}@a.com", f"Big Org {self._n}")

        oversized_body = b"id\n" + b"1\n" * 6_000_000
        r = self._upload(headers, f"Big CSV {self._n}", "big_table", body=oversized_body)
        self.assertEqual(r.status_code, 400)

    def test_malformed_csv_rejected(self):
        headers = self._register_and_login(f"mal{self._n}@a.com", f"Malformed Org {self._n}")

        r = self._upload(headers, f"Malformed CSV {self._n}", "empty_table", body=b"id,name\n")
        self.assertEqual(r.status_code, 400)

    def test_tenant_scoping_org_b_cannot_see_org_a_upload(self):
        headers_a = self._register_and_login(f"tena{self._n}@a.com", f"Tenant A Org {self._n}")
        headers_b = self._register_and_login(f"tenb{self._n}@a.com", f"Tenant B Org {self._n}")

        r = self._upload(headers_a, f"Tenant A CSV {self._n}", "tenant_a_table")
        self.assertEqual(r.status_code, 200, r.text)

        r = self.client.get("/api/sources", headers=headers_b)
        self.assertEqual(r.json(), [])

        r = self.client.get("/api/datasets", headers=headers_b)
        self.assertEqual(r.json(), [])

    def test_upload_requires_admin_or_steward_role(self):
        headers = self._register_and_login(f"vwr{self._n}@a.com", f"Viewer Org {self._n}")

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

        r = self._upload(viewer_headers, f"Viewer CSV {self._n}", "viewer_table")
        self.assertEqual(r.status_code, 403)


if __name__ == "__main__":
    unittest.main()
