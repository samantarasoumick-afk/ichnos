"""
Columns are now part of the searchable catalog corpus
(app/services/catalog_search_service.py) - GET /api/search and the "@"
mention picker (GET /api/mentions) should both be able to surface a
specific column, not just the dataset it lives on.
"""

import unittest
import uuid

from fastapi.testclient import TestClient

from app.db.database import SessionLocal
from app.main import app
from app.models.column import DatasetColumn
from app.models.dataset import Dataset
from app.models.organization import Organization
from app.models.source import DataSource


class ColumnSearchTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)

    def setUp(self):
        self._n = uuid.uuid4().hex[:8]
        self.db = SessionLocal()

    def tearDown(self):
        self.db.close()

    def _register_and_login(self, email, org_name):
        r = self.client.post("/api/auth/register", json={
            "email": email, "password": "password123", "organization_name": org_name,
        })
        self.assertEqual(r.status_code, 200, r.text)
        r = self.client.post("/api/auth/login", json={"email": email, "password": "password123"})
        token = r.json()["access_token"]
        return {"Authorization": f"Bearer {token}"}, r

    def _seed_dataset_with_column(self, org_id, column_name, column_kwargs=None):
        source = DataSource(name="Warehouse", type="postgresql", connection_config={}, organization_id=org_id)
        self.db.add(source)
        self.db.flush()

        dataset = Dataset(name="customers", schema_name="public", source_id=source.id, organization_id=org_id)
        self.db.add(dataset)
        self.db.flush()

        column = DatasetColumn(
            dataset_id=dataset.id,
            name=column_name,
            data_type="string",
            **(column_kwargs or {}),
        )
        self.db.add(column)
        self.db.commit()

        return dataset, column

    def test_column_appears_in_global_search_with_dataset_context(self):
        headers, _ = self._register_and_login(f"colsearch{self._n}@a.com", f"Col Search Org {self._n}")

        # Pull the freshly-registered user's organization_id straight
        # from the DB rather than guessing at an endpoint shape - the
        # test only needs it to seed a dataset/column in the same org.
        from app.models.user import User
        user = self.db.query(User).filter(User.email == f"colsearch{self._n}@a.com").first()
        self.assertIsNotNone(user)

        column_name = f"loyalty_tier_{self._n}"
        dataset, column = self._seed_dataset_with_column(
            user.organization_id, column_name, {"classification": "SENSITIVE", "description": "Customer loyalty tier"}
        )

        r = self.client.get(f"/api/search?q={column_name}", headers=headers)
        self.assertEqual(r.status_code, 200, r.text)

        results = r.json()["results"]
        column_hits = [item for item in results if item["type"] == "column"]
        self.assertEqual(len(column_hits), 1, results)

        hit = column_hits[0]
        self.assertEqual(hit["id"], column.id)
        self.assertEqual(hit["label"], column_name)
        self.assertIn("public.customers", hit["subtitle"])
        self.assertIn("SENSITIVE", hit["subtitle"])
        self.assertEqual(hit["url"], f"/datasets/{dataset.id}?tab=columns&highlightColumn={column.id}")

    def test_column_search_does_not_leak_sample_values(self):
        headers, _ = self._register_and_login(f"colsearchleak{self._n}@a.com", f"Col Search Leak Org {self._n}")

        from app.models.user import User
        user = self.db.query(User).filter(User.email == f"colsearchleak{self._n}@a.com").first()

        secret_marker = f"SECRETSAMPLE{self._n}"
        column_name = f"ssn_{self._n}"
        self._seed_dataset_with_column(
            user.organization_id,
            column_name,
            {"classification": "PII", "sample_values": f'["{secret_marker}"]'},
        )

        r = self.client.get(f"/api/search?q={secret_marker}", headers=headers)
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["results"], [])

    def test_column_appears_in_mention_picker(self):
        headers, _ = self._register_and_login(f"colmention{self._n}@a.com", f"Col Mention Org {self._n}")

        from app.models.user import User
        user = self.db.query(User).filter(User.email == f"colmention{self._n}@a.com").first()

        column_name = f"churnscore{self._n}"
        _, column = self._seed_dataset_with_column(user.organization_id, column_name)

        r = self.client.get(f"/api/mentions?q={column_name}", headers=headers)
        self.assertEqual(r.status_code, 200, r.text)

        results = r.json()["results"]
        matches = [item for item in results if item["type"] == "column" and item["id"] == column.id]
        self.assertEqual(len(matches), 1, results)

    def test_column_search_is_tenant_scoped(self):
        headers_a, _ = self._register_and_login(f"coltenanta{self._n}@a.com", f"Col Tenant A {self._n}")

        from app.models.user import User
        user_a = self.db.query(User).filter(User.email == f"coltenanta{self._n}@a.com").first()

        column_name = f"crosstenantcol{self._n}"
        self._seed_dataset_with_column(user_a.organization_id, column_name)

        headers_b, _ = self._register_and_login(f"coltenantb{self._n}@a.com", f"Col Tenant B {self._n}")
        r = self.client.get(f"/api/search?q={column_name}", headers=headers_b)
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["results"], [])


if __name__ == "__main__":
    unittest.main()
