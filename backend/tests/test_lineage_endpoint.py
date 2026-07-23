"""
Regression test for GET/POST /api/lineage: both routes used to be
registered only at the trailing-slash path ("/"), but the frontend
(and this test, matching real client behavior) calls the bare
"/api/lineage" - triggering a 307 redirect that drops the Authorization
header, so every request came back 401 and the Lineage page always
showed an error. Same bug class as datasets/columns/audit-log/
data-quality, just missed in the original sweep because these two
decorators are written across multiple lines.
"""

import unittest
import uuid

from fastapi.testclient import TestClient

from app.main import app


class LineageEndpointTests(unittest.TestCase):

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

    def test_list_lineage_without_trailing_slash_does_not_401(self):
        headers = self._register_and_login(f"lin{self._n}@a.com", f"Lineage Org {self._n}")

        # No trailing slash, exactly as the frontend's axios client calls it.
        r = self.client.get("/api/lineage", headers=headers)
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json(), [])

    def test_create_and_list_lineage_end_to_end(self):
        headers = self._register_and_login(f"lin2{self._n}@a.com", f"Lineage Org2 {self._n}")

        # Create two datasets directly via the DB, same as other tests
        # do when they don't need a real scan.
        from app.db.database import SessionLocal
        from app.models.dataset import Dataset
        from app.models.user import User

        db = SessionLocal()
        try:
            me = db.query(User).filter(User.email == f"lin2{self._n}@a.com").first()

            r = self.client.post("/api/sources", headers=headers, json={
                "name": f"Source2 {self._n}",
                "type": "postgresql",
                "connection_config": {"host": "x"},
            })
            source_id = r.json()["id"]

            upstream = Dataset(
                name="upstream_table",
                schema_name="public",
                source_id=source_id,
                organization_id=me.organization_id,
            )
            downstream = Dataset(
                name="downstream_table",
                schema_name="public",
                source_id=source_id,
                organization_id=me.organization_id,
            )
            db.add_all([upstream, downstream])
            db.commit()
            db.refresh(upstream)
            db.refresh(downstream)
            upstream_id, downstream_id = upstream.id, downstream.id
        finally:
            db.close()

        r = self.client.post("/api/lineage", headers=headers, json={
            "upstream_dataset_id": upstream_id,
            "downstream_dataset_id": downstream_id,
            "transformation_type": "etl",
        })
        self.assertEqual(r.status_code, 200, r.text)

        r = self.client.get("/api/lineage", headers=headers)
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(len(r.json()), 1)
        self.assertEqual(r.json()[0]["transformation_type"], "etl")

        r = self.client.get(f"/api/lineage/{downstream_id}/dependencies", headers=headers)
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(len(r.json()), 1)
        self.assertEqual(r.json()[0]["upstream_dataset_id"], upstream_id)

        r = self.client.get(f"/api/lineage/{upstream_id}/impact", headers=headers)
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(len(r.json()), 1)
        self.assertEqual(r.json()[0]["downstream_dataset_id"], downstream_id)


if __name__ == "__main__":
    unittest.main()
