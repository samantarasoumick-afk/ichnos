"""
Tests for GET /api/reports/compliance: it should return a real PDF
scoped to the caller's organization only, and log an audit event for
the export (compliance reports are exactly the kind of action you
want a paper trail for).
"""

import unittest
import uuid

from fastapi.testclient import TestClient

from app.main import app
from app.db.database import SessionLocal
from app.models.dataset import Dataset
from app.models.user import User


class ComplianceReportTests(unittest.TestCase):

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

    def test_report_with_no_datasets_still_returns_a_pdf(self):
        headers = self._register_and_login(f"empty{self._n}@a.com", f"Empty Org {self._n}")

        r = self.client.get("/api/reports/compliance", headers=headers)
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.headers["content-type"], "application/pdf")
        self.assertTrue(r.content.startswith(b"%PDF"))

    def test_report_includes_datasets_and_logs_audit_event(self):
        headers = self._register_and_login(f"rep{self._n}@a.com", f"Report Org {self._n}")

        db = SessionLocal()
        try:
            me = db.query(User).filter(User.email == f"rep{self._n}@a.com").first()
            db.add(Dataset(
                name="widgets",
                schema_name="public",
                organization_id=me.organization_id,
                owner="Data Platform",
                certification="VERIFIED",
            ))
            db.commit()
        finally:
            db.close()

        r = self.client.get("/api/reports/compliance", headers=headers)
        self.assertEqual(r.status_code, 200, r.text)
        self.assertTrue(r.content.startswith(b"%PDF"))
        self.assertGreater(len(r.content), 1000, "PDF should have real content, not just a stub")

        r = self.client.get("/api/audit-log", headers=headers)
        actions = [entry["action"] for entry in r.json()]
        self.assertIn("report.export", actions)

    def test_report_requires_auth(self):
        r = self.client.get("/api/reports/compliance")
        self.assertEqual(r.status_code, 401)

    def test_report_is_tenant_scoped(self):
        headers_a = self._register_and_login(f"tenA{self._n}@a.com", f"Tenant A {self._n}")
        headers_b = self._register_and_login(f"tenB{self._n}@b.com", f"Tenant B {self._n}")

        db = SessionLocal()
        try:
            user_a = db.query(User).filter(User.email == f"tenA{self._n}@a.com").first()
            db.add(Dataset(
                name="only_in_a",
                schema_name="public",
                organization_id=user_a.organization_id,
            ))
            db.commit()
        finally:
            db.close()

        r_a = self.client.get("/api/reports/compliance", headers=headers_a)
        r_b = self.client.get("/api/reports/compliance", headers=headers_b)

        # Org B has no datasets, so its report should be meaningfully
        # smaller than org A's (which has one) - a cheap proxy for
        # "org B's PDF doesn't contain org A's data" without needing
        # to parse PDF internals.
        self.assertGreater(len(r_a.content), len(r_b.content))


if __name__ == "__main__":
    unittest.main()
