"""
Integration tests for POST /api/governance/glossary/bulk-import - the
scoped bulk-upload capability: CSV in, many BusinessGlossaryTerm rows
out, without needing to hand-create each one via the single-term
endpoint. Covers the happy path, partial success (some rows skipped,
not the whole import failing), duplicate detection against both
existing terms and repeats within the same file, missing required
columns, non-CSV rejection, and role gating.
"""

import io
import unittest
import uuid

from fastapi.testclient import TestClient

from app.main import app


class GlossaryBulkImportTests(unittest.TestCase):

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

    def _upload_csv(self, headers, csv_text, filename="terms.csv"):
        return self.client.post(
            "/api/governance/glossary/bulk-import",
            headers=headers,
            files={"file": (filename, csv_text.encode("utf-8"), "text/csv")},
        )

    def test_bulk_import_creates_all_valid_rows(self):
        headers = self._register_and_login(f"gbi1{self._n}@a.com", f"Bulk Org 1 {self._n}")

        csv_text = (
            "term,definition,domain,owner,status\n"
            f"Customer {self._n},A person or company that purchased something.,Sales,Growth Team,ACTIVE\n"
            f"Order {self._n},A confirmed purchase transaction.,Sales,Growth Team,\n"
        )

        r = self._upload_csv(headers, csv_text)
        self.assertEqual(r.status_code, 200, r.text)
        body = r.json()

        self.assertEqual(body["created_count"], 2)
        self.assertEqual(body["skipped_count"], 0)
        terms = {t["term"]: t for t in body["created"]}
        self.assertEqual(terms[f"Customer {self._n}"]["status"], "ACTIVE")
        # Blank status in the CSV falls back to DRAFT, same default as
        # the single-term create endpoint.
        self.assertEqual(terms[f"Order {self._n}"]["status"], "DRAFT")

        r = self.client.get("/api/governance/glossary", headers=headers)
        listed_terms = {t["term"] for t in r.json()}
        self.assertIn(f"Customer {self._n}", listed_terms)
        self.assertIn(f"Order {self._n}", listed_terms)

    def test_missing_required_field_is_skipped_not_fatal(self):
        headers = self._register_and_login(f"gbi2{self._n}@a.com", f"Bulk Org 2 {self._n}")

        csv_text = (
            "term,definition\n"
            f"Good Term {self._n},A perfectly fine definition.\n"
            ",Missing a term name.\n"
            f"Also Missing {self._n},\n"
        )

        r = self._upload_csv(headers, csv_text)
        self.assertEqual(r.status_code, 200, r.text)
        body = r.json()

        self.assertEqual(body["created_count"], 1)
        self.assertEqual(body["skipped_count"], 2)
        self.assertEqual(body["created"][0]["term"], f"Good Term {self._n}")
        for skipped in body["skipped"]:
            self.assertIn("Missing term or definition", skipped["reason"])

    def test_duplicate_against_existing_term_and_within_file_are_both_skipped(self):
        headers = self._register_and_login(f"gbi3{self._n}@a.com", f"Bulk Org 3 {self._n}")

        r = self.client.post("/api/governance/glossary", headers=headers, json={
            "term": f"Existing Term {self._n}",
            "definition": "Already here before the import.",
        })
        self.assertEqual(r.status_code, 200, r.text)

        csv_text = (
            "term,definition\n"
            f"Existing Term {self._n},A duplicate of an existing term.\n"
            f"Brand New {self._n},First time seeing this one.\n"
            f"Brand New {self._n},A second row with the exact same term.\n"
        )

        r = self._upload_csv(headers, csv_text)
        self.assertEqual(r.status_code, 200, r.text)
        body = r.json()

        self.assertEqual(body["created_count"], 1)
        self.assertEqual(body["skipped_count"], 2)
        self.assertEqual(body["created"][0]["term"], f"Brand New {self._n}")

    def test_missing_required_columns_rejected(self):
        headers = self._register_and_login(f"gbi4{self._n}@a.com", f"Bulk Org 4 {self._n}")

        csv_text = "name,notes\nSomething,Not the right columns\n"

        r = self._upload_csv(headers, csv_text)
        self.assertEqual(r.status_code, 400)
        self.assertIn("term", r.json()["detail"])

    def test_non_csv_file_rejected(self):
        headers = self._register_and_login(f"gbi5{self._n}@a.com", f"Bulk Org 5 {self._n}")

        r = self.client.post(
            "/api/governance/glossary/bulk-import",
            headers=headers,
            files={"file": ("terms.txt", b"term,definition\nA,B\n", "text/plain")},
        )
        self.assertEqual(r.status_code, 400)

    def test_bulk_import_is_tenant_scoped_for_duplicate_detection(self):
        headers_a = self._register_and_login(f"gbi6a{self._n}@a.com", f"Bulk Org 6A {self._n}")
        headers_b = self._register_and_login(f"gbi6b{self._n}@a.com", f"Bulk Org 6B {self._n}")

        self.client.post("/api/governance/glossary", headers=headers_a, json={
            "term": f"Shared Name {self._n}",
            "definition": "Defined in org A.",
        })

        csv_text = f"term,definition\nShared Name {self._n},Defined independently in org B.\n"
        r = self._upload_csv(headers_b, csv_text)
        self.assertEqual(r.status_code, 200, r.text)
        # Same term name, but a different org - not a duplicate there.
        self.assertEqual(r.json()["created_count"], 1)

    def test_role_gating_viewer_cannot_bulk_import(self):
        headers = self._register_and_login(f"gbi7{self._n}@a.com", f"Bulk Org 7 {self._n}")

        r = self.client.post("/api/users", headers=headers, json={
            "email": f"gbiviewer{self._n}@a.com",
            "password": "password123",
            "role": "viewer",
        })
        self.assertEqual(r.status_code, 200, r.text)

        r = self.client.post("/api/auth/login", json={
            "email": f"gbiviewer{self._n}@a.com",
            "password": "password123",
        })
        viewer_headers = {"Authorization": f"Bearer {r.json()['access_token']}"}

        csv_text = f"term,definition\nViewer Term {self._n},Should not be allowed.\n"
        r = self._upload_csv(viewer_headers, csv_text)
        self.assertEqual(r.status_code, 403)


if __name__ == "__main__":
    unittest.main()
