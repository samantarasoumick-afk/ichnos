"""
Team management: inviting members into an existing organization,
role changes, and the "can't remove the last admin" / "deactivated
users can't authenticate" guards.
"""

import unittest
import uuid

from fastapi.testclient import TestClient

from app.main import app


class TeamManagementTests(unittest.TestCase):

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
        self.assertEqual(r.status_code, 200, r.text)

        return {"Authorization": f"Bearer {r.json()['access_token']}"}

    def test_admin_can_invite_member_into_same_org(self):
        admin_headers = self._register_and_login(f"admin{self._n}@a.com", f"Org {self._n}")

        r = self.client.post("/api/users", headers=admin_headers, json={
            "email": f"steward{self._n}@a.com",
            "password": "password123",
            "role": "steward",
        })
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["role"], "steward")
        self.assertTrue(r.json()["is_active"])

        # the new member can log in and see the same org's data
        r = self.client.post("/api/auth/login", json={
            "email": f"steward{self._n}@a.com",
            "password": "password123",
        })
        self.assertEqual(r.status_code, 200, r.text)
        member_headers = {"Authorization": f"Bearer {r.json()['access_token']}"}

        r = self.client.get("/api/auth/me", headers=member_headers)
        admin_me = self.client.get("/api/auth/me", headers=admin_headers).json()
        self.assertEqual(r.json()["organization_id"], admin_me["organization_id"])

        r = self.client.get("/api/users", headers=member_headers)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(len(r.json()), 2)

    def test_non_admin_cannot_invite(self):
        admin_headers = self._register_and_login(f"admin2{self._n}@a.com", f"Org2 {self._n}")

        self.client.post("/api/users", headers=admin_headers, json={
            "email": f"viewer{self._n}@a.com",
            "password": "password123",
            "role": "viewer",
        })
        r = self.client.post("/api/auth/login", json={
            "email": f"viewer{self._n}@a.com",
            "password": "password123",
        })
        viewer_headers = {"Authorization": f"Bearer {r.json()['access_token']}"}

        r = self.client.post("/api/users", headers=viewer_headers, json={
            "email": f"another{self._n}@a.com",
            "password": "password123",
            "role": "viewer",
        })
        self.assertEqual(r.status_code, 403)

    def test_invite_rejects_duplicate_email(self):
        admin_headers = self._register_and_login(f"admin3{self._n}@a.com", f"Org3 {self._n}")

        r = self.client.post("/api/users", headers=admin_headers, json={
            "email": f"admin3{self._n}@a.com",
            "password": "password123",
            "role": "viewer",
        })
        self.assertEqual(r.status_code, 400)

    def test_invite_rejects_invalid_role(self):
        admin_headers = self._register_and_login(f"admin4{self._n}@a.com", f"Org4 {self._n}")

        r = self.client.post("/api/users", headers=admin_headers, json={
            "email": f"bad-role{self._n}@a.com",
            "password": "password123",
            "role": "superuser",
        })
        self.assertEqual(r.status_code, 400)

    def test_cannot_demote_or_deactivate_last_admin(self):
        admin_headers = self._register_and_login(f"soleadmin{self._n}@a.com", f"Org5 {self._n}")
        me = self.client.get("/api/auth/me", headers=admin_headers).json()

        r = self.client.patch(f"/api/users/{me['id']}", headers=admin_headers, json={
            "role": "viewer",
        })
        self.assertEqual(r.status_code, 400)

        r = self.client.patch(f"/api/users/{me['id']}", headers=admin_headers, json={
            "is_active": False,
        })
        self.assertEqual(r.status_code, 400)

    def test_can_demote_admin_when_another_admin_exists(self):
        admin_headers = self._register_and_login(f"first{self._n}@a.com", f"Org6 {self._n}")

        r = self.client.post("/api/users", headers=admin_headers, json={
            "email": f"second{self._n}@a.com",
            "password": "password123",
            "role": "admin",
        })
        second_id = r.json()["id"]

        r = self.client.patch(f"/api/users/{second_id}", headers=admin_headers, json={
            "role": "viewer",
        })
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["role"], "viewer")

    def test_deactivated_user_cannot_login_or_use_existing_token(self):
        admin_headers = self._register_and_login(f"admin7{self._n}@a.com", f"Org7 {self._n}")

        r = self.client.post("/api/users", headers=admin_headers, json={
            "email": f"tobedeactivated{self._n}@a.com",
            "password": "password123",
            "role": "viewer",
        })
        member_id = r.json()["id"]

        r = self.client.post("/api/auth/login", json={
            "email": f"tobedeactivated{self._n}@a.com",
            "password": "password123",
        })
        member_headers = {"Authorization": f"Bearer {r.json()['access_token']}"}

        # token is valid before deactivation
        r = self.client.get("/api/auth/me", headers=member_headers)
        self.assertEqual(r.status_code, 200)

        r = self.client.patch(f"/api/users/{member_id}", headers=admin_headers, json={
            "is_active": False,
        })
        self.assertEqual(r.status_code, 200, r.text)

        # existing token is now rejected
        r = self.client.get("/api/auth/me", headers=member_headers)
        self.assertEqual(r.status_code, 401)

        # fresh login attempt is also rejected
        r = self.client.post("/api/auth/login", json={
            "email": f"tobedeactivated{self._n}@a.com",
            "password": "password123",
        })
        self.assertEqual(r.status_code, 401)

    def test_tenant_isolation_on_team_listing(self):
        headers_a = self._register_and_login(f"orga{self._n}@a.com", f"OrgA8 {self._n}")
        headers_b = self._register_and_login(f"orgb{self._n}@b.com", f"OrgB8 {self._n}")

        r = self.client.get("/api/users", headers=headers_a)
        emails_a = {member["email"] for member in r.json()}
        self.assertIn(f"orga{self._n}@a.com", emails_a)
        self.assertNotIn(f"orgb{self._n}@b.com", emails_a)

        r = self.client.get("/api/users", headers=headers_b)
        emails_b = {member["email"] for member in r.json()}
        self.assertIn(f"orgb{self._n}@b.com", emails_b)
        self.assertNotIn(f"orga{self._n}@a.com", emails_b)


if __name__ == "__main__":
    unittest.main()
