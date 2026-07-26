"""
Platform admin API (app/api/platform.py): the require_platform_admin
gate rejecting ordinary org admins, the cross-org organizations
list/detail rollups, suspend/activate (including that a suspended
org's existing token stops working immediately), and the manual plan
override used for Enterprise/custom deals. is_platform_admin is never
grantable through any API (see User model docstring) - tests flip it
directly via SessionLocal, the same direct-DB-access pattern
test_login_lockout.py established.
"""

import unittest
import uuid

from fastapi.testclient import TestClient

from app.main import app
from app.db.database import SessionLocal
from app.models.user import User


class PlatformAdminTestsBase(unittest.TestCase):

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

        headers = {"Authorization": f"Bearer {r.json()['access_token']}"}
        me = self.client.get("/api/auth/me", headers=headers).json()

        return headers, me["organization_id"], me["id"]

    def _make_platform_admin(self, user_id):
        db = SessionLocal()
        try:
            user = db.query(User).filter(User.id == user_id).first()
            user.is_platform_admin = True
            db.commit()
        finally:
            db.close()


class PlatformAdminGateTests(PlatformAdminTestsBase):

    def test_ordinary_org_admin_is_forbidden(self):
        headers, _, _ = self._register_and_login(f"admin{self._n}@a.com", f"PA Org {self._n}")

        r = self.client.get("/api/platform/organizations", headers=headers)
        self.assertEqual(r.status_code, 403)

    def test_me_reports_is_platform_admin_flag(self):
        headers, _, user_id = self._register_and_login(
            f"admin2{self._n}@a.com", f"PA Org2 {self._n}"
        )

        r = self.client.get("/api/auth/me", headers=headers)
        self.assertFalse(r.json()["is_platform_admin"])

        self._make_platform_admin(user_id)

        r = self.client.get("/api/auth/me", headers=headers)
        self.assertTrue(r.json()["is_platform_admin"])


class PlatformAdminOrganizationsTests(PlatformAdminTestsBase):

    def test_list_organizations_includes_this_org_with_expected_shape(self):
        headers, organization_id, user_id = self._register_and_login(
            f"admin3{self._n}@a.com", f"PA Org3 {self._n}"
        )
        self._make_platform_admin(user_id)

        r = self.client.get("/api/platform/organizations", headers=headers)
        self.assertEqual(r.status_code, 200, r.text)

        orgs = {org["id"]: org for org in r.json()}
        self.assertIn(organization_id, orgs)

        entry = orgs[organization_id]
        self.assertEqual(entry["plan"], "starter")
        self.assertEqual(entry["plan_status"], "trialing")
        self.assertFalse(entry["is_suspended"])
        self.assertEqual(entry["real_source_count"], 0)
        self.assertFalse(entry["demo_data_loaded"])

    def test_get_organization_detail_includes_members(self):
        headers, organization_id, user_id = self._register_and_login(
            f"admin4{self._n}@a.com", f"PA Org4 {self._n}"
        )
        self._make_platform_admin(user_id)

        r = self.client.get(f"/api/platform/organizations/{organization_id}", headers=headers)
        self.assertEqual(r.status_code, 200, r.text)

        detail = r.json()
        self.assertEqual(detail["id"], organization_id)
        self.assertEqual(len(detail["members"]), 1)
        self.assertEqual(detail["members"][0]["email"], f"admin4{self._n}@a.com")

    def test_get_organization_detail_404_for_unknown_id(self):
        headers, _, user_id = self._register_and_login(
            f"admin5{self._n}@a.com", f"PA Org5 {self._n}"
        )
        self._make_platform_admin(user_id)

        r = self.client.get("/api/platform/organizations/not-a-real-id", headers=headers)
        self.assertEqual(r.status_code, 404)

    def test_suspend_blocks_further_authenticated_requests_for_that_org(self):
        admin_headers, organization_id, admin_id = self._register_and_login(
            f"admin6{self._n}@a.com", f"PA Org6 {self._n}"
        )
        self._make_platform_admin(admin_id)

        # A second, separate platform-admin-flagged account does the
        # suspending, so the suspended org's own token is what's being
        # tested below, not the actor's.
        other_headers, _, other_id = self._register_and_login(
            f"operator{self._n}@a.com", f"PA Operator Org {self._n}"
        )
        self._make_platform_admin(other_id)

        r = self.client.post(
            f"/api/platform/organizations/{organization_id}/suspend", headers=other_headers
        )
        self.assertEqual(r.status_code, 200, r.text)
        self.assertTrue(r.json()["is_suspended"])

        r = self.client.get("/api/auth/me", headers=admin_headers)
        self.assertEqual(r.status_code, 403)
        self.assertIn("suspended", r.json()["detail"])

        r = self.client.post(
            f"/api/platform/organizations/{organization_id}/activate", headers=other_headers
        )
        self.assertEqual(r.status_code, 200, r.text)
        self.assertFalse(r.json()["is_suspended"])

        r = self.client.get("/api/auth/me", headers=admin_headers)
        self.assertEqual(r.status_code, 200)

    def test_suspend_unknown_org_404s(self):
        headers, _, user_id = self._register_and_login(
            f"admin7{self._n}@a.com", f"PA Org7 {self._n}"
        )
        self._make_platform_admin(user_id)

        r = self.client.post("/api/platform/organizations/not-a-real-id/suspend", headers=headers)
        self.assertEqual(r.status_code, 404)

    def test_manual_plan_override(self):
        headers, organization_id, user_id = self._register_and_login(
            f"admin8{self._n}@a.com", f"PA Org8 {self._n}"
        )
        self._make_platform_admin(user_id)

        r = self.client.patch(
            f"/api/platform/organizations/{organization_id}/plan",
            headers=headers,
            json={"plan": "enterprise", "billing_cycle": "yearly", "plan_status": "active"},
        )
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["plan"], "enterprise")
        self.assertEqual(r.json()["plan_status"], "active")

        r = self.client.get(f"/api/platform/organizations/{organization_id}", headers=headers)
        self.assertEqual(r.json()["plan"], "enterprise")
        self.assertEqual(r.json()["billing_cycle"], "yearly")

    def test_marketing_funnel_returns_expected_shape(self):
        headers, _, user_id = self._register_and_login(
            f"admin9{self._n}@a.com", f"PA Org9 {self._n}"
        )
        self._make_platform_admin(user_id)

        r = self.client.get("/api/platform/marketing/funnel?days=30", headers=headers)
        self.assertEqual(r.status_code, 200, r.text)

        body = r.json()
        self.assertEqual(body["window_days"], 30)
        for key in (
            "pageviews", "unique_visitors", "signups_started",
            "signups_completed", "visitor_to_signup_rate", "signups_by_source",
        ):
            self.assertIn(key, body)


if __name__ == "__main__":
    unittest.main()
