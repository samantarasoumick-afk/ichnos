"""
Plan entitlements: the pure get_entitlements()/effective_entitlements()
branching logic, plus the three API-layer enforcement points (source
cap, seat cap, Ask/day cap) actually rejecting requests once an org is
past its plan's limit. Every new signup defaults to plan_status
"trialing" (open caps - see entitlements.py's "trial" profile), so
these tests deliberately flip an org to plan_status="active" via
direct DB access (same pattern test_login_lockout.py uses) to exercise
the real, capped-down starter tier rather than the trial's open one.
"""

import unittest
import uuid
from datetime import datetime, timedelta

from fastapi.testclient import TestClient

from app.main import app
from app.db.database import SessionLocal
from app.models.organization import Organization
from app.models.query_log import QueryLog
from app.services import entitlements


class EntitlementsUnitTests(unittest.TestCase):

    def test_get_entitlements_known_plans(self):
        for plan in entitlements.PLANS:
            result = entitlements.get_entitlements(plan)
            self.assertEqual(result.plan, plan)

    def test_get_entitlements_falls_back_to_starter_for_unknown_plan(self):
        result = entitlements.get_entitlements("not-a-real-plan")
        self.assertEqual(result.plan, "starter")

    def test_get_entitlements_falls_back_to_starter_for_none(self):
        result = entitlements.get_entitlements(None)
        self.assertEqual(result.plan, "starter")

    def test_effective_entitlements_trialing_is_open_regardless_of_plan(self):
        org = Organization(plan="starter", plan_status="trialing")
        result = entitlements.effective_entitlements(org)
        self.assertEqual(result.plan, "trial")
        self.assertIsNone(result.max_sources)

    def test_effective_entitlements_active_uses_real_plan_caps(self):
        org = Organization(plan="team", plan_status="active")
        result = entitlements.effective_entitlements(org)
        self.assertEqual(result.plan, "team")
        self.assertEqual(result.max_sources, 5)

    def test_effective_entitlements_canceled_falls_back_to_starter(self):
        org = Organization(plan="business", plan_status="canceled")
        result = entitlements.effective_entitlements(org)
        self.assertEqual(result.plan, "starter")

    def test_effective_entitlements_past_due_falls_back_to_starter(self):
        org = Organization(plan="enterprise", plan_status="past_due")
        result = entitlements.effective_entitlements(org)
        self.assertEqual(result.plan, "starter")

    def test_is_feature_enabled_reflects_effective_plan(self):
        org = Organization(plan="starter", plan_status="active")
        self.assertFalse(entitlements.is_feature_enabled(org, "column_lineage"))

        org.plan = "business"
        self.assertTrue(entitlements.is_feature_enabled(org, "column_lineage"))

    def test_is_feature_enabled_unknown_feature_is_false(self):
        org = Organization(plan="enterprise", plan_status="active")
        self.assertFalse(entitlements.is_feature_enabled(org, "not_a_real_feature"))


class EntitlementsEnforcementTests(unittest.TestCase):

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

        return headers, me["organization_id"]

    def _set_active_starter(self, organization_id):
        """
        Flips an org off the open trial and onto starter's real caps
        (1 source, 1 hard-capped seat, 20 Ask questions/day) - see
        this module's docstring.
        """

        db = SessionLocal()
        try:
            org = db.query(Organization).filter(Organization.id == organization_id).first()
            org.plan = "starter"
            org.plan_status = "active"
            db.commit()
        finally:
            db.close()

    def test_source_creation_blocked_past_starter_cap(self):
        headers, organization_id = self._register_and_login(
            f"admin{self._n}@a.com", f"EntOrg {self._n}"
        )
        self._set_active_starter(organization_id)

        r = self.client.post("/api/sources", headers=headers, json={
            "name": f"Source A {self._n}",
            "type": "postgres",
            "connection_config": {"host": "localhost"},
        })
        self.assertEqual(r.status_code, 200, r.text)

        r = self.client.post("/api/sources", headers=headers, json={
            "name": f"Source B {self._n}",
            "type": "postgres",
            "connection_config": {"host": "localhost"},
        })
        self.assertEqual(r.status_code, 402, r.text)
        self.assertIn("starter plan", r.json()["detail"])

    def test_seed_sources_do_not_count_against_the_cap(self):
        # Regression guard for the bug this originally caused (see
        # session history: entitlements initially counted demo-seeded
        # sources, which made the seeder itself trip a fresh trial
        # org's cap). Not directly testable without the demo seeder
        # here, so this asserts the DataSource.is_seed_data exclusion
        # in enforce_source_limit directly at the model/query level
        # instead of re-running the whole seeder.
        headers, organization_id = self._register_and_login(
            f"admin2{self._n}@a.com", f"EntOrg2 {self._n}"
        )
        self._set_active_starter(organization_id)

        db = SessionLocal()
        try:
            from app.models.source import DataSource
            db.add(DataSource(
                name=f"Demo Source {self._n}",
                type="postgres",
                connection_config={},
                organization_id=organization_id,
                is_seed_data=True,
            ))
            db.commit()
        finally:
            db.close()

        # The org now has 1 seed source but 0 real ones - starter's
        # 1-real-source cap should still allow exactly one real create.
        r = self.client.post("/api/sources", headers=headers, json={
            "name": f"Real Source {self._n}",
            "type": "postgres",
            "connection_config": {},
        })
        self.assertEqual(r.status_code, 200, r.text)

    def test_invite_blocked_past_starter_seat_cap(self):
        headers, organization_id = self._register_and_login(
            f"admin3{self._n}@a.com", f"EntOrg3 {self._n}"
        )
        self._set_active_starter(organization_id)

        # The admin themself already fills starter's 1-seat cap -
        # inviting any non-viewer should be rejected immediately.
        r = self.client.post("/api/users", headers=headers, json={
            "email": f"steward{self._n}@a.com",
            "password": "password123",
            "role": "steward",
        })
        self.assertEqual(r.status_code, 402, r.text)
        self.assertIn("editor seat", r.json()["detail"])

    def test_viewer_invites_never_blocked_by_seat_cap(self):
        headers, organization_id = self._register_and_login(
            f"admin4{self._n}@a.com", f"EntOrg4 {self._n}"
        )
        self._set_active_starter(organization_id)

        r = self.client.post("/api/users", headers=headers, json={
            "email": f"viewer{self._n}@a.com",
            "password": "password123",
            "role": "viewer",
        })
        self.assertEqual(r.status_code, 200, r.text)

    def test_ask_blocked_past_daily_limit(self):
        headers, organization_id = self._register_and_login(
            f"admin5{self._n}@a.com", f"EntOrg5 {self._n}"
        )
        self._set_active_starter(organization_id)

        db = SessionLocal()
        try:
            me_id = self.client.get("/api/auth/me", headers=headers).json()["id"]
            for _ in range(20):  # starter's ask_daily_limit
                db.add(QueryLog(
                    organization_id=organization_id,
                    actor_user_id=me_id,
                    source="ask",
                    query_text="What is this dataset?",
                    matched=True,
                    created_at=datetime.utcnow(),
                ))
            db.commit()
        finally:
            db.close()

        r = self.client.post(
            "/api/assistant/ask", headers=headers, json={"query": "What is this dataset?"}
        )
        self.assertEqual(r.status_code, 429, r.text)
        self.assertIn("starter plan", r.json()["detail"])

    def test_ask_not_blocked_by_stale_usage_outside_24h_window(self):
        headers, organization_id = self._register_and_login(
            f"admin6{self._n}@a.com", f"EntOrg6 {self._n}"
        )
        self._set_active_starter(organization_id)

        db = SessionLocal()
        try:
            me_id = self.client.get("/api/auth/me", headers=headers).json()["id"]
            for _ in range(20):
                db.add(QueryLog(
                    organization_id=organization_id,
                    actor_user_id=me_id,
                    source="ask",
                    query_text="What is this dataset?",
                    matched=True,
                    created_at=datetime.utcnow() - timedelta(hours=30),
                ))
            db.commit()
        finally:
            db.close()

        r = self.client.post(
            "/api/assistant/ask", headers=headers, json={"query": "What is this dataset?"}
        )
        # Not blocked by the cost guard - may still fail/succeed on its
        # own merits downstream, but never a 429.
        self.assertNotEqual(r.status_code, 429, r.text)


if __name__ == "__main__":
    unittest.main()
