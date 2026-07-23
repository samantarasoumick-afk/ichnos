"""
Integration tests for the audit trail and privacy overview endpoints,
driven through the real FastAPI app (only the Postgres connection is
mocked, same pattern as test_scan_column_diffing.py).
"""

import unittest
import uuid
from datetime import datetime, timedelta
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import app


SCAN_RESULT = {
    "datasets": [{
        "schema_name": "public",
        "table_name": "customers",
        "columns": [
            ("id", "integer", "NO"),
            ("email", "text", "YES"),
        ],
        "row_count": 2,
        "column_stats": {
            "id": {"non_null": 2, "distinct": 2},
            "email": {"non_null": 2, "distinct": 2},
        },
        "column_samples": {
            "id": ["1", "2"],
            "email": ["a@b.com", "c@d.com"],
        },
    }],
    "foreign_keys": [],
}


class AuditAndPrivacyApiTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)

    def setUp(self):
        unique = uuid.uuid4().hex[:8]
        self.email = f"admin-{unique}@privacy-test.com"

        r = self.client.post("/api/auth/register", json={
            "email": self.email,
            "password": "password123",
            "organization_name": f"Privacy Test Org {unique}",
        })
        self.assertEqual(r.status_code, 200, r.text)

        r = self.client.post("/api/auth/login", json={
            "email": self.email,
            "password": "password123",
        })
        self.headers = {"Authorization": f"Bearer {r.json()['access_token']}"}

    def test_register_and_login_are_audited(self):
        r = self.client.get("/api/audit-log/", headers=self.headers)
        self.assertEqual(r.status_code, 200, r.text)
        actions = [entry["action"] for entry in r.json()]
        self.assertIn("user.register", actions)
        self.assertIn("user.login", actions)

    def test_source_create_and_scan_are_audited(self):
        r = self.client.post("/api/sources", headers=self.headers, json={
            "name": f"Audit Test Source {uuid.uuid4().hex[:6]}",
            "type": "postgresql",
            "connection_config": {"host": "x", "database": "y", "user": "z", "password": "p", "port": 5432},
        })
        source_id = r.json()["id"]

        with patch("app.api.scanner.get_scanner", return_value=lambda config: SCAN_RESULT):
            r = self.client.post(f"/api/scanner/{source_id}", headers=self.headers)
        self.assertEqual(r.status_code, 200, r.text)

        r = self.client.get("/api/audit-log/", headers=self.headers)
        actions = [entry["action"] for entry in r.json()]
        self.assertIn("source.create", actions)
        self.assertIn("scanner.scan", actions)

    def test_audit_log_is_tenant_scoped(self):
        # A second org's audit log must not include anything from
        # this test's org (registered in setUp).
        other_email = f"other-{uuid.uuid4().hex[:8]}@privacy-test.com"
        self.client.post("/api/auth/register", json={
            "email": other_email,
            "password": "password123",
            "organization_name": f"Other Org {uuid.uuid4().hex[:8]}",
        })
        r = self.client.post("/api/auth/login", json={"email": other_email, "password": "password123"})
        other_headers = {"Authorization": f"Bearer {r.json()['access_token']}"}

        r = self.client.get("/api/audit-log/", headers=other_headers)
        actions = [entry["action"] for entry in r.json()]
        # the only audit events visible to the "other" org are its own
        # register/login, never this test's source.create/scanner.scan
        self.assertNotIn("source.create", actions)
        self.assertNotIn("scanner.scan", actions)

    def test_audit_log_filters_by_action_and_actor(self):
        r = self.client.post("/api/sources", headers=self.headers, json={
            "name": f"Audit Filter Source {uuid.uuid4().hex[:6]}",
            "type": "postgresql",
            "connection_config": {"host": "x", "database": "y", "user": "z", "password": "p", "port": 5432},
        })
        self.assertEqual(r.status_code, 200, r.text)

        # Filtering by a substring of the action name should return
        # only matching rows - not require an exact match.
        r = self.client.get(
            "/api/audit-log/", headers=self.headers, params={"action": "source.create"}
        )
        self.assertEqual(r.status_code, 200, r.text)
        entries = r.json()
        self.assertTrue(len(entries) > 0)
        self.assertTrue(all(e["action"] == "source.create" for e in entries))

        # Filtering by actor (case-insensitive substring of the email)
        # should still find this user's own entries.
        r = self.client.get(
            "/api/audit-log/", headers=self.headers,
            params={"actor": self.email.split("@")[0].upper()},
        )
        self.assertEqual(r.status_code, 200, r.text)
        self.assertTrue(len(r.json()) > 0)

        # An action filter that matches nothing returns an empty list,
        # not an error.
        r = self.client.get(
            "/api/audit-log/", headers=self.headers,
            params={"action": "definitely_not_a_real_action"},
        )
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json(), [])

    def test_audit_log_filters_by_date_range(self):
        # Every entry for this fresh org was created "now" - a date
        # range covering today should include them, and a range
        # entirely in the past should exclude them.
        today = datetime.utcnow().date().isoformat()
        tomorrow = (datetime.utcnow().date() + timedelta(days=1)).isoformat()
        last_year = (datetime.utcnow().date() - timedelta(days=365)).isoformat()
        two_years_ago = (datetime.utcnow().date() - timedelta(days=730)).isoformat()

        r = self.client.get(
            "/api/audit-log/", headers=self.headers,
            params={"date_from": today, "date_to": tomorrow},
        )
        self.assertEqual(r.status_code, 200, r.text)
        self.assertTrue(len(r.json()) > 0)

        r = self.client.get(
            "/api/audit-log/", headers=self.headers,
            params={"date_from": two_years_ago, "date_to": last_year},
        )
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json(), [])

    def test_audit_log_export_returns_csv_matching_filters(self):
        r = self.client.get(
            "/api/audit-log/export", headers=self.headers, params={"action": "user.register"}
        )
        self.assertEqual(r.status_code, 200, r.text)
        self.assertIn("text/csv", r.headers["content-type"])
        self.assertIn("attachment", r.headers["content-disposition"])

        body = r.text
        lines = [line for line in body.splitlines() if line]
        self.assertEqual(lines[0], "created_at,actor_email,action,resource_type,resource_id,details")
        self.assertTrue(any("user.register" in line for line in lines[1:]))
        self.assertTrue(all("scanner.scan" not in line for line in lines[1:]))

    def test_audit_log_export_is_tenant_scoped(self):
        other_email = f"export-other-{uuid.uuid4().hex[:8]}@privacy-test.com"
        self.client.post("/api/auth/register", json={
            "email": other_email,
            "password": "password123",
            "organization_name": f"Export Other Org {uuid.uuid4().hex[:8]}",
        })
        r = self.client.post("/api/auth/login", json={"email": other_email, "password": "password123"})
        other_headers = {"Authorization": f"Bearer {r.json()['access_token']}"}

        r = self.client.get("/api/audit-log/export", headers=other_headers)
        self.assertEqual(r.status_code, 200, r.text)
        self.assertNotIn(self.email, r.text)

    def test_privacy_overview_reflects_scanned_pii(self):
        r = self.client.post("/api/sources", headers=self.headers, json={
            "name": f"Privacy Overview Source {uuid.uuid4().hex[:6]}",
            "type": "postgresql",
            "connection_config": {"host": "x", "database": "y", "user": "z", "password": "p", "port": 5432},
        })
        source_id = r.json()["id"]

        with patch("app.api.scanner.get_scanner", return_value=lambda config: SCAN_RESULT):
            r = self.client.post(f"/api/scanner/{source_id}", headers=self.headers)
        self.assertEqual(r.status_code, 200, r.text)

        r = self.client.get("/api/privacy/overview", headers=self.headers)
        self.assertEqual(r.status_code, 200, r.text)
        overview = r.json()

        self.assertGreaterEqual(overview["total_datasets"], 1)
        # the scanned "email" column requires consent and consent_status
        # defaults to NOT_ASSESSED, so this dataset should show up as
        # needing consent review and drag the average score down.
        self.assertGreaterEqual(overview["datasets_needing_consent_review"], 1)
        self.assertLess(overview["average_privacy_score"], 100)
        self.assertIn("contact", overview["sensitive_columns_by_dpdp_category"])

    def test_governance_update_can_set_purpose_and_consent(self):
        r = self.client.post("/api/sources", headers=self.headers, json={
            "name": f"Governance Update Source {uuid.uuid4().hex[:6]}",
            "type": "postgresql",
            "connection_config": {"host": "x", "database": "y", "user": "z", "password": "p", "port": 5432},
        })
        source_id = r.json()["id"]

        with patch("app.api.scanner.get_scanner", return_value=lambda config: SCAN_RESULT):
            self.client.post(f"/api/scanner/{source_id}", headers=self.headers)

        r = self.client.get("/api/datasets/", headers=self.headers)
        dataset_id = r.json()[0]["id"]

        r = self.client.patch(
            f"/api/governance/datasets/{dataset_id}",
            headers=self.headers,
            json={
                "purpose": "Customer relationship management",
                "consent_status": "CONSENT_OBTAINED",
                "retention_period_days": 730,
            },
        )
        self.assertEqual(r.status_code, 200, r.text)
        body = r.json()
        self.assertEqual(body["purpose"], "Customer relationship management")
        self.assertEqual(body["consent_status"], "CONSENT_OBTAINED")
        self.assertEqual(body["retention_status"], "WITHIN_POLICY")
        self.assertEqual(body["privacy_score"], 100)

        r = self.client.get("/api/audit-log/", headers=self.headers)
        actions = [entry["action"] for entry in r.json()]
        self.assertIn("governance.update", actions)


if __name__ == "__main__":
    unittest.main()
