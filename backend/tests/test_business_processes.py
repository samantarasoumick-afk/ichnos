"""
Integration tests for /api/business-processes - the "process
dimension": a business-facing taxonomy (Order-to-Cash, Customer
Onboarding, ...) datasets get tagged with, independent of (and
many-to-many unlike) the single free-text `domain` field already on
Dataset. Covers CRUD, duplicate-name rejection, linking/unlinking
datasets in both directions, dataset_count staying accurate, deleting
a process cleaning up its links, tenant scoping, and role gating.
"""

import unittest
import uuid

from fastapi.testclient import TestClient

from app.main import app


class BusinessProcessTests(unittest.TestCase):

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

    def _create_process(self, headers, name="Order-to-Cash"):
        r = self.client.post("/api/business-processes", headers=headers, json={
            "name": f"{name} {self._n}",
            "description": "From placing an order through to collecting payment.",
            "owner": "Revenue Ops",
        })
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()

    def _create_dataset(self, headers, table_name="orders", source_suffix=""):
        csv_bytes = b"order_id,total\n1,10.00\n2,20.00\n"
        r = self.client.post(
            "/api/sources/upload",
            headers=headers,
            data={"name": f"src-{table_name}-{self._n}{source_suffix}", "table_name": table_name, "schema_name": "public"},
            files={"file": (f"{table_name}.csv", csv_bytes, "text/csv")},
        )
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()["dataset_id"]

    def test_create_and_list_processes(self):
        headers = self._register_and_login(f"bp1{self._n}@a.com", f"Process Org 1 {self._n}")
        process = self._create_process(headers)

        r = self.client.get("/api/business-processes", headers=headers)
        self.assertEqual(r.status_code, 200, r.text)
        names = [p["name"] for p in r.json()]
        self.assertIn(process["name"], names)
        self.assertEqual(process["dataset_count"], 0)

    def test_duplicate_name_rejected(self):
        headers = self._register_and_login(f"bp2{self._n}@a.com", f"Process Org 2 {self._n}")
        self._create_process(headers, name="Procure-to-Pay")

        r = self.client.post("/api/business-processes", headers=headers, json={
            "name": f"Procure-to-Pay {self._n}",
            "description": "duplicate",
        })
        self.assertEqual(r.status_code, 400)

    def test_update_process(self):
        headers = self._register_and_login(f"bp3{self._n}@a.com", f"Process Org 3 {self._n}")
        process = self._create_process(headers)

        r = self.client.patch(f"/api/business-processes/{process['id']}", headers=headers, json={
            "owner": "Finance Ops",
        })
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["owner"], "Finance Ops")
        self.assertEqual(r.json()["name"], process["name"])

    def test_link_and_unlink_dataset_updates_dataset_count(self):
        headers = self._register_and_login(f"bp4{self._n}@a.com", f"Process Org 4 {self._n}")
        process = self._create_process(headers)
        dataset_id = self._create_dataset(headers)

        r = self.client.post(f"/api/business-processes/{process['id']}/datasets", headers=headers, json={
            "dataset_id": dataset_id,
        })
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["process_name"], process["name"])

        r = self.client.get("/api/business-processes", headers=headers)
        updated = next(p for p in r.json() if p["id"] == process["id"])
        self.assertEqual(updated["dataset_count"], 1)

        r = self.client.delete(f"/api/business-processes/{process['id']}/datasets/{dataset_id}", headers=headers)
        self.assertEqual(r.status_code, 200, r.text)

        r = self.client.get("/api/business-processes", headers=headers)
        updated = next(p for p in r.json() if p["id"] == process["id"])
        self.assertEqual(updated["dataset_count"], 0)

    def test_duplicate_dataset_link_rejected(self):
        headers = self._register_and_login(f"bp5{self._n}@a.com", f"Process Org 5 {self._n}")
        process = self._create_process(headers)
        dataset_id = self._create_dataset(headers)

        payload = {"dataset_id": dataset_id}
        r = self.client.post(f"/api/business-processes/{process['id']}/datasets", headers=headers, json=payload)
        self.assertEqual(r.status_code, 200, r.text)

        r = self.client.post(f"/api/business-processes/{process['id']}/datasets", headers=headers, json=payload)
        self.assertEqual(r.status_code, 400)

    def test_list_datasets_for_process_and_processes_for_dataset(self):
        headers = self._register_and_login(f"bp6{self._n}@a.com", f"Process Org 6 {self._n}")
        process_a = self._create_process(headers, name="Order-to-Cash")
        process_b = self._create_process(headers, name="Customer Onboarding")
        dataset_id = self._create_dataset(headers)

        self.client.post(f"/api/business-processes/{process_a['id']}/datasets", headers=headers, json={"dataset_id": dataset_id})
        self.client.post(f"/api/business-processes/{process_b['id']}/datasets", headers=headers, json={"dataset_id": dataset_id})

        r = self.client.get(f"/api/business-processes/{process_a['id']}/datasets", headers=headers)
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(len(r.json()), 1)
        self.assertEqual(r.json()[0]["id"], dataset_id)

        r = self.client.get(f"/api/business-processes/dataset/{dataset_id}", headers=headers)
        self.assertEqual(r.status_code, 200, r.text)
        process_names = {p["name"] for p in r.json()}
        self.assertEqual(process_names, {process_a["name"], process_b["name"]})

    def test_delete_process_removes_its_links(self):
        headers = self._register_and_login(f"bp7{self._n}@a.com", f"Process Org 7 {self._n}")
        process = self._create_process(headers)
        dataset_id = self._create_dataset(headers)

        self.client.post(f"/api/business-processes/{process['id']}/datasets", headers=headers, json={"dataset_id": dataset_id})

        r = self.client.delete(f"/api/business-processes/{process['id']}", headers=headers)
        self.assertEqual(r.status_code, 200, r.text)

        r = self.client.get(f"/api/business-processes/dataset/{dataset_id}", headers=headers)
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json(), [])

    def test_tenant_scoping(self):
        headers_a = self._register_and_login(f"bp8a{self._n}@a.com", f"Process Org 8a {self._n}")
        headers_b = self._register_and_login(f"bp8b{self._n}@a.com", f"Process Org 8b {self._n}")

        process_a = self._create_process(headers_a)
        dataset_a = self._create_dataset(headers_a)

        r = self.client.post(f"/api/business-processes/{process_a['id']}/datasets", headers=headers_b, json={"dataset_id": dataset_a})
        self.assertEqual(r.status_code, 404)

        r = self.client.get("/api/business-processes", headers=headers_b)
        self.assertEqual(r.json(), [])

    def test_narrative_field_round_trips(self):
        headers = self._register_and_login(f"bp10{self._n}@a.com", f"Process Org 10 {self._n}")

        r = self.client.post("/api/business-processes", headers=headers, json={
            "name": f"Order-to-Cash {self._n}",
            "narrative": "A Customer (Master) orders (Transactional) from a Store (Master) in Mumbai (Reference).",
        })
        self.assertEqual(r.status_code, 200, r.text)
        process = r.json()
        self.assertIn("Customer (Master)", process["narrative"])

        r = self.client.patch(f"/api/business-processes/{process['id']}", headers=headers, json={
            "narrative": "Updated narrative.",
        })
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["narrative"], "Updated narrative.")

    def test_linking_dataset_to_process_autocreates_glossary_term(self):
        headers = self._register_and_login(f"bp11{self._n}@a.com", f"Process Org 11 {self._n}")
        process = self._create_process(headers)
        dataset_id = self._create_dataset(headers, table_name="orders")

        r = self.client.post(f"/api/business-processes/{process['id']}/datasets", headers=headers, json={
            "dataset_id": dataset_id,
        })
        self.assertEqual(r.status_code, 200, r.text)
        body = r.json()
        self.assertTrue(body["glossary_term_created"])
        self.assertEqual(body["glossary_term_name"], "Orders")

        r = self.client.get(f"/api/glossary-links/dataset/{dataset_id}", headers=headers)
        self.assertEqual(r.status_code, 200, r.text)
        terms = [link["term"] for link in r.json()]
        self.assertIn("Orders", terms)

        r = self.client.get("/api/governance/glossary", headers=headers)
        self.assertEqual(r.status_code, 200, r.text)
        orders_term = next(t for t in r.json() if t["term"] == "Orders")
        self.assertEqual(orders_term["status"], "DRAFT")

    def test_linking_second_dataset_with_same_name_reuses_glossary_term(self):
        headers = self._register_and_login(f"bp12{self._n}@a.com", f"Process Org 12 {self._n}")
        process = self._create_process(headers)
        dataset_1 = self._create_dataset(headers, table_name="customer", source_suffix="-a")
        dataset_2 = self._create_dataset(headers, table_name="customer", source_suffix="-b")

        r1 = self.client.post(f"/api/business-processes/{process['id']}/datasets", headers=headers, json={
            "dataset_id": dataset_1,
        })
        self.assertTrue(r1.json()["glossary_term_created"])

        r2 = self.client.post(f"/api/business-processes/{process['id']}/datasets", headers=headers, json={
            "dataset_id": dataset_2,
        })
        self.assertEqual(r2.status_code, 200, r2.text)
        self.assertFalse(r2.json()["glossary_term_created"])
        self.assertEqual(r2.json()["glossary_term_name"], "Customer")

        r = self.client.get("/api/governance/glossary", headers=headers)
        customer_terms = [t for t in r.json() if t["term"] == "Customer"]
        self.assertEqual(len(customer_terms), 1)

    def test_dataset_summary_for_process_includes_data_category(self):
        headers = self._register_and_login(f"bp13{self._n}@a.com", f"Process Org 13 {self._n}")
        process = self._create_process(headers)
        dataset_id = self._create_dataset(headers, table_name="orders")

        self.client.post(f"/api/business-processes/{process['id']}/datasets", headers=headers, json={
            "dataset_id": dataset_id,
        })

        r = self.client.get(f"/api/business-processes/{process['id']}/datasets", headers=headers)
        self.assertEqual(r.status_code, 200, r.text)
        self.assertIn("data_category", r.json()[0])

    def test_role_gating(self):
        headers = self._register_and_login(f"bp9{self._n}@a.com", f"Process Org 9 {self._n}")

        r = self.client.post("/api/users", headers=headers, json={
            "email": f"bpviewer{self._n}@a.com",
            "password": "password123",
            "role": "viewer",
        })
        self.assertEqual(r.status_code, 200, r.text)

        r = self.client.post("/api/auth/login", json={
            "email": f"bpviewer{self._n}@a.com",
            "password": "password123",
        })
        viewer_headers = {"Authorization": f"Bearer {r.json()['access_token']}"}

        r = self.client.post("/api/business-processes", headers=viewer_headers, json={
            "name": f"Viewer Process {self._n}",
        })
        self.assertEqual(r.status_code, 403)

        r = self.client.get("/api/business-processes", headers=viewer_headers)
        self.assertEqual(r.status_code, 200, r.text)


if __name__ == "__main__":
    unittest.main()
