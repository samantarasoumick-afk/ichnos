"""
Integration tests for POST/GET/DELETE /api/glossary-links - the
explicit connection between a BusinessGlossaryTerm and the technical
catalog that didn't exist before (previously the only relationship
between a term and a dataset was coincidental term-overlap in the Ask
Assistant's semantic search, not a real link). Covers both link
granularities (whole dataset vs. one specific column), duplicate
rejection for each, 404s for cross-tenant/unknown references, listing
from both the dataset side and the term side, deletion, and role
gating.
"""

import unittest
import uuid

from fastapi.testclient import TestClient

from app.main import app


class GlossaryLinkTests(unittest.TestCase):

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

    def _create_term(self, headers, term="Customer"):
        r = self.client.post("/api/governance/glossary", headers=headers, json={
            "term": f"{term} {self._n}",
            "definition": "A person or company that has purchased something from us.",
            "domain": "Sales",
            "owner": "Data Governance",
        })
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()

    def _create_dataset_with_column(self, headers, table_name="customers"):
        csv_bytes = b"customer_id,email\n1,a@b.com\n2,c@d.com\n"
        r = self.client.post(
            "/api/sources/upload",
            headers=headers,
            data={"name": f"src-{table_name}-{self._n}", "table_name": table_name, "schema_name": "public"},
            files={"file": (f"{table_name}.csv", csv_bytes, "text/csv")},
        )
        self.assertEqual(r.status_code, 200, r.text)
        dataset_id = r.json()["dataset_id"]

        r = self.client.get(f"/api/columns/dataset/{dataset_id}", headers=headers)
        columns = {c["name"]: c["id"] for c in r.json()}

        return dataset_id, columns

    def test_create_dataset_level_link(self):
        headers = self._register_and_login(f"gl1{self._n}@a.com", f"Glossary Org 1 {self._n}")
        term = self._create_term(headers)
        dataset_id, _columns = self._create_dataset_with_column(headers)

        r = self.client.post("/api/glossary-links", headers=headers, json={
            "term_id": term["id"],
            "dataset_id": dataset_id,
        })
        self.assertEqual(r.status_code, 200, r.text)
        body = r.json()
        self.assertEqual(body["term_id"], term["id"])
        self.assertEqual(body["dataset_id"], dataset_id)
        self.assertIsNone(body["column_id"])
        self.assertEqual(body["term"], term["term"])
        self.assertEqual(body["definition"], term["definition"])
        # The bug this guards against: a dataset-level link used to
        # come back with no way to tell which dataset it pointed at
        # (the frontend fell back to literally rendering "dataset").
        self.assertEqual(body["dataset_schema_name"], "public")
        self.assertEqual(body["dataset_name"], "customers")

    def test_create_column_level_link(self):
        headers = self._register_and_login(f"gl2{self._n}@a.com", f"Glossary Org 2 {self._n}")
        term = self._create_term(headers, term="Email Address")
        dataset_id, columns = self._create_dataset_with_column(headers)

        r = self.client.post("/api/glossary-links", headers=headers, json={
            "term_id": term["id"],
            "dataset_id": dataset_id,
            "column_id": columns["email"],
        })
        self.assertEqual(r.status_code, 200, r.text)
        body = r.json()
        self.assertEqual(body["column_id"], columns["email"])
        self.assertEqual(body["column_name"], "email")

    def test_duplicate_dataset_level_link_rejected(self):
        headers = self._register_and_login(f"gl3{self._n}@a.com", f"Glossary Org 3 {self._n}")
        term = self._create_term(headers)
        dataset_id, _columns = self._create_dataset_with_column(headers)

        payload = {"term_id": term["id"], "dataset_id": dataset_id}
        r = self.client.post("/api/glossary-links", headers=headers, json=payload)
        self.assertEqual(r.status_code, 200, r.text)

        r = self.client.post("/api/glossary-links", headers=headers, json=payload)
        self.assertEqual(r.status_code, 400)

    def test_duplicate_column_level_link_rejected(self):
        headers = self._register_and_login(f"gl4{self._n}@a.com", f"Glossary Org 4 {self._n}")
        term = self._create_term(headers)
        dataset_id, columns = self._create_dataset_with_column(headers)

        payload = {"term_id": term["id"], "dataset_id": dataset_id, "column_id": columns["email"]}
        r = self.client.post("/api/glossary-links", headers=headers, json=payload)
        self.assertEqual(r.status_code, 200, r.text)

        r = self.client.post("/api/glossary-links", headers=headers, json=payload)
        self.assertEqual(r.status_code, 400)

    def test_dataset_and_column_level_links_can_coexist_for_same_term(self):
        """
        A term can describe the whole dataset AND, separately, pin to
        one exact column on it - these are two distinct links, not a
        conflict.
        """
        headers = self._register_and_login(f"gl5{self._n}@a.com", f"Glossary Org 5 {self._n}")
        term = self._create_term(headers)
        dataset_id, columns = self._create_dataset_with_column(headers)

        r = self.client.post("/api/glossary-links", headers=headers, json={
            "term_id": term["id"], "dataset_id": dataset_id,
        })
        self.assertEqual(r.status_code, 200, r.text)

        r = self.client.post("/api/glossary-links", headers=headers, json={
            "term_id": term["id"], "dataset_id": dataset_id, "column_id": columns["email"],
        })
        self.assertEqual(r.status_code, 200, r.text)

        r = self.client.get(f"/api/glossary-links/dataset/{dataset_id}", headers=headers)
        self.assertEqual(len(r.json()), 2)

    def test_link_rejects_unknown_term_or_dataset_or_column(self):
        headers = self._register_and_login(f"gl6{self._n}@a.com", f"Glossary Org 6 {self._n}")
        term = self._create_term(headers)
        dataset_id, columns = self._create_dataset_with_column(headers)
        other_dataset_id, other_columns = self._create_dataset_with_column(headers, table_name="orders")

        r = self.client.post("/api/glossary-links", headers=headers, json={
            "term_id": str(uuid.uuid4()), "dataset_id": dataset_id,
        })
        self.assertEqual(r.status_code, 404)

        r = self.client.post("/api/glossary-links", headers=headers, json={
            "term_id": term["id"], "dataset_id": str(uuid.uuid4()),
        })
        self.assertEqual(r.status_code, 404)

        # A column that exists, but on a different dataset than the
        # one named in the request.
        r = self.client.post("/api/glossary-links", headers=headers, json={
            "term_id": term["id"], "dataset_id": dataset_id, "column_id": other_columns["customer_id"],
        })
        self.assertEqual(r.status_code, 404)

        del columns  # unused beyond setup

    def test_list_links_for_dataset_and_for_term(self):
        headers = self._register_and_login(f"gl7{self._n}@a.com", f"Glossary Org 7 {self._n}")
        term = self._create_term(headers)
        dataset_id, columns = self._create_dataset_with_column(headers)

        self.client.post("/api/glossary-links", headers=headers, json={
            "term_id": term["id"], "dataset_id": dataset_id, "column_id": columns["email"],
        })

        r = self.client.get(f"/api/glossary-links/dataset/{dataset_id}", headers=headers)
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(len(r.json()), 1)
        self.assertEqual(r.json()[0]["dataset_name"], "customers")

        r = self.client.get(f"/api/glossary-links/term/{term['id']}", headers=headers)
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(len(r.json()), 1)
        self.assertEqual(r.json()[0]["dataset_schema_name"], "public")

    def test_delete_link(self):
        headers = self._register_and_login(f"gl8{self._n}@a.com", f"Glossary Org 8 {self._n}")
        term = self._create_term(headers)
        dataset_id, _columns = self._create_dataset_with_column(headers)

        r = self.client.post("/api/glossary-links", headers=headers, json={
            "term_id": term["id"], "dataset_id": dataset_id,
        })
        link_id = r.json()["id"]

        r = self.client.delete(f"/api/glossary-links/{link_id}", headers=headers)
        self.assertEqual(r.status_code, 200, r.text)

        r = self.client.get(f"/api/glossary-links/dataset/{dataset_id}", headers=headers)
        self.assertEqual(r.json(), [])

    def test_tenant_scoping(self):
        headers_a = self._register_and_login(f"gl9a{self._n}@a.com", f"Glossary Org 9a {self._n}")
        headers_b = self._register_and_login(f"gl9b{self._n}@a.com", f"Glossary Org 9b {self._n}")

        term_a = self._create_term(headers_a)
        dataset_a, _columns = self._create_dataset_with_column(headers_a)

        # Org B can't link using org A's term or dataset ids.
        r = self.client.post("/api/glossary-links", headers=headers_b, json={
            "term_id": term_a["id"], "dataset_id": dataset_a,
        })
        self.assertEqual(r.status_code, 404)

        # Org B can't list org A's dataset's links either.
        r = self.client.get(f"/api/glossary-links/dataset/{dataset_a}", headers=headers_b)
        self.assertEqual(r.status_code, 404)

    def test_role_gating(self):
        headers = self._register_and_login(f"gl10{self._n}@a.com", f"Glossary Org 10 {self._n}")
        term = self._create_term(headers)
        dataset_id, _columns = self._create_dataset_with_column(headers)

        r = self.client.post("/api/users", headers=headers, json={
            "email": f"glviewer{self._n}@a.com",
            "password": "password123",
            "role": "viewer",
        })
        self.assertEqual(r.status_code, 200, r.text)

        r = self.client.post("/api/auth/login", json={
            "email": f"glviewer{self._n}@a.com",
            "password": "password123",
        })
        viewer_headers = {"Authorization": f"Bearer {r.json()['access_token']}"}

        r = self.client.post("/api/glossary-links", headers=viewer_headers, json={
            "term_id": term["id"], "dataset_id": dataset_id,
        })
        self.assertEqual(r.status_code, 403)

        # Viewers can still read.
        r = self.client.get(f"/api/glossary-links/dataset/{dataset_id}", headers=viewer_headers)
        self.assertEqual(r.status_code, 200, r.text)


if __name__ == "__main__":
    unittest.main()
