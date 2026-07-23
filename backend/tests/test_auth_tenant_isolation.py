"""
End-to-end regression test for the multi-tenant security foundation:
auth is enforced, tenants can't see each other's data, roles are
gated, and secrets are encrypted at rest.

Run directly with:
    SECRET_KEY=... ENCRYPTION_KEY=... DATABASE_URL=sqlite:////tmp/test.db \
        python -m pytest backend/tests/test_auth_tenant_isolation.py -v

or let conftest.py supply throwaway values (see below) and just run:
    pytest backend/tests/test_auth_tenant_isolation.py -v
"""

import unittest

from fastapi.testclient import TestClient

from app.db.database import SessionLocal
from app.main import app
from app.models.user import User
from app.auth.security import hash_password

from conftest import _DB_PATH


class AuthAndTenantIsolationTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)

    def setUp(self):
        # unique emails/org names per test so tests can run in any order
        self._n = id(self)

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
        self.assertEqual(r.status_code, 200, r.text)

        token = r.json()["access_token"]
        return {"Authorization": f"Bearer {token}"}

    def test_registration_and_login(self):
        headers = self._register_and_login(f"admin{self._n}@a.com", f"Org A {self._n}")
        self.assertIn("Authorization", headers)

        r = self.client.post("/api/auth/login", json={
            "email": f"admin{self._n}@a.com",
            "password": "wrong-password",
        })
        self.assertEqual(r.status_code, 401)

    def test_unauthenticated_requests_are_rejected(self):
        r = self.client.get("/api/sources")
        self.assertEqual(r.status_code, 401)

        r = self.client.get("/api/sources", headers={"Authorization": "Bearer not-a-real-token"})
        self.assertEqual(r.status_code, 401)

    def test_tenant_isolation_on_sources_and_glossary(self):
        headers_a = self._register_and_login(f"alice{self._n}@a.com", f"Org A {self._n}")
        headers_b = self._register_and_login(f"bob{self._n}@b.com", f"Org B {self._n}")

        r = self.client.post("/api/sources", headers=headers_a, json={
            "name": f"OrgA Prod DB {self._n}",
            "type": "postgresql",
            "connection_config": {"host": "prod.a.internal", "user": "a", "password": "s3cr3t"},
        })
        self.assertEqual(r.status_code, 200, r.text)
        source_a_id = r.json()["id"]

        r = self.client.get("/api/sources", headers=headers_a)
        self.assertEqual(len(r.json()), 1)

        r = self.client.get("/api/sources", headers=headers_b)
        self.assertEqual(r.json(), [], "org B must not see org A's sources")

        r = self.client.post(f"/api/scanner/{source_a_id}", headers=headers_b)
        self.assertEqual(r.status_code, 404, "org B must not be able to target org A's source id")

        self.client.post("/api/governance/glossary", headers=headers_a, json={
            "term": f"Customer{self._n}",
            "definition": "A paying account holder",
        })
        r = self.client.get("/api/governance/glossary", headers=headers_b)
        self.assertEqual(r.json(), [], "org B must not see org A's glossary terms")

    def test_connection_config_is_encrypted_at_rest(self):
        headers_a = self._register_and_login(f"carol{self._n}@a.com", f"Org C {self._n}")

        secret_marker = f"s3cret-marker-{self._n}"
        self.client.post("/api/sources", headers=headers_a, json={
            "name": f"Encrypted Source {self._n}",
            "type": "postgresql",
            "connection_config": {"host": "internal.example", "password": secret_marker},
        })

        with open(_DB_PATH, "rb") as f:
            raw = f.read()
        self.assertNotIn(secret_marker.encode(), raw)

        r = self.client.get("/api/sources", headers=headers_a)
        configs = [s["connection_config"]["password"] for s in r.json() if s["name"] == f"Encrypted Source {self._n}"]
        self.assertEqual(configs, [secret_marker], "value must decrypt correctly through the API")

    def test_viewer_role_is_read_only(self):
        headers_a = self._register_and_login(f"dave{self._n}@a.com", f"Org D {self._n}")

        db = SessionLocal()
        admin_user = db.query(User).filter(User.email == f"dave{self._n}@a.com").first()
        viewer = User(
            email=f"viewer{self._n}@a.com",
            password_hash=hash_password("password123"),
            role="viewer",
            organization_id=admin_user.organization_id,
        )
        db.add(viewer)
        db.commit()
        db.close()

        r = self.client.post("/api/auth/login", json={
            "email": f"viewer{self._n}@a.com",
            "password": "password123",
        })
        headers_viewer = {"Authorization": f"Bearer {r.json()['access_token']}"}

        r = self.client.post("/api/sources", headers=headers_viewer, json={
            "name": "Should not be created",
            "type": "postgresql",
            "connection_config": {"host": "x"},
        })
        self.assertEqual(r.status_code, 403)

        r = self.client.get("/api/sources", headers=headers_viewer)
        self.assertEqual(r.status_code, 200)


class AuthMeEndpointTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)

    def test_me_returns_current_user_and_org(self):
        unique = __import__("uuid").uuid4().hex[:8]
        email = f"me-{unique}@a.com"

        r = self.client.post("/api/auth/register", json={
            "email": email,
            "password": "password123",
            "organization_name": f"Me Org {unique}",
        })
        self.assertEqual(r.status_code, 200, r.text)

        r = self.client.post("/api/auth/login", json={"email": email, "password": "password123"})
        headers = {"Authorization": f"Bearer {r.json()['access_token']}"}

        r = self.client.get("/api/auth/me", headers=headers)
        self.assertEqual(r.status_code, 200, r.text)
        body = r.json()
        self.assertEqual(body["email"], email)
        self.assertEqual(body["role"], "admin")
        self.assertEqual(body["organization_name"], f"Me Org {unique}")

    def test_me_requires_auth(self):
        r = self.client.get("/api/auth/me")
        self.assertEqual(r.status_code, 401)


if __name__ == "__main__":
    unittest.main()
