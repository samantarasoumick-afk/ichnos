"""
Tests for the Risk register + Control library: creating/scoring risks
(inherent score from likelihood x impact, residual score after linked
EFFECTIVE controls), linking risks to datasets/processes/controls,
tenant scoping, RBAC, and the risk-coverage dimension this feeds into
the org-level governance maturity score.
"""

import unittest
import uuid
from unittest.mock import patch, MagicMock

from fastapi.testclient import TestClient

from app.db.database import SessionLocal
from app.main import app
from app.models.dataset import Dataset
from app.models.user import User


PII_SCAN_RESULT = {
    "datasets": [{
        "schema_name": "public",
        "table_name": "customers",
        "columns": [
            ("id", "integer", "NO"),
            ("email", "text", "YES"),
            ("phone", "text", "YES"),
        ],
        "row_count": 2,
        "column_stats": {
            "id": {"non_null": 2, "distinct": 2},
            "email": {"non_null": 2, "distinct": 2},
            "phone": {"non_null": 2, "distinct": 2},
        },
        "column_samples": {
            "id": ["1", "2"],
            "email": ["a@b.com", "c@d.com"],
            "phone": ["9876543210", "9123456780"],
        },
    }],
    "foreign_keys": [],
}


class RisksAndControlsTests(unittest.TestCase):

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

    def _invite(self, admin_headers, email, role):
        r = self.client.post("/api/users", headers=admin_headers, json={
            "email": email,
            "password": "password123",
            "role": role,
        })
        self.assertEqual(r.status_code, 200, r.text)

        r = self.client.post("/api/auth/login", json={
            "email": email,
            "password": "password123",
        })
        return {"Authorization": f"Bearer {r.json()['access_token']}"}

    def _create_bare_dataset(self, email):
        db = SessionLocal()
        try:
            me = db.query(User).filter(User.email == email).first()

            r = self.client.post("/api/sources", headers=self._headers_cache[email], json={
                "name": f"Source {self._n}",
                "type": "postgresql",
                "connection_config": {"host": "x"},
            })
            source_id = r.json()["id"]

            dataset = Dataset(
                name="orders", schema_name="public",
                source_id=source_id, organization_id=me.organization_id,
            )
            db.add(dataset)
            db.commit()
            db.refresh(dataset)
            return dataset.id
        finally:
            db.close()

    @patch("app.api.scanner.get_scanner")
    def _create_high_sensitivity_dataset(self, headers, mock_get_scanner):
        mock_get_scanner.return_value = MagicMock(return_value=PII_SCAN_RESULT)

        r = self.client.post("/api/sources", headers=headers, json={
            "name": f"PII Source {self._n}",
            "type": "postgresql",
            "connection_config": {"host": "x", "database": "y", "user": "z", "password": "p"},
        })
        source_id = r.json()["id"]

        r = self.client.post(f"/api/scanner/{source_id}", headers=headers)
        self.assertEqual(r.status_code, 200, r.text)

        return self.client.get("/api/datasets", headers=headers).json()[0]["id"]

    def _create_risk(self, headers, likelihood="MEDIUM", impact="MEDIUM", **extra):
        r = self.client.post("/api/risks", headers=headers, json={
            "title": f"Risk {self._n}",
            "category": "PRIVACY",
            "likelihood": likelihood,
            "impact": impact,
            **extra,
        })
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()

    def _create_control(self, headers, **extra):
        r = self.client.post("/api/controls", headers=headers, json={
            "name": f"Control {self._n}",
            "control_type": "PREVENTIVE",
            **extra,
        })
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()

    # -- scoring -----------------------------------------------------

    def test_inherent_score_from_likelihood_and_impact(self):
        headers = self._register_and_login(f"rc1{self._n}@a.com", f"RC Org 1 {self._n}")

        risk = self._create_risk(headers, likelihood="HIGH", impact="HIGH")
        self.assertEqual(risk["inherent_score"], 9)
        self.assertEqual(risk["inherent_level"], "HIGH")
        # No controls linked yet - residual equals inherent.
        self.assertEqual(risk["residual_score"], 9)
        self.assertEqual(risk["residual_level"], "HIGH")
        self.assertEqual(risk["effective_control_count"], 0)

    def test_residual_score_drops_as_effective_controls_are_linked(self):
        headers = self._register_and_login(f"rc2{self._n}@a.com", f"RC Org 2 {self._n}")

        risk = self._create_risk(headers, likelihood="HIGH", impact="HIGH")
        control = self._create_control(headers)

        # Not yet EFFECTIVE - shouldn't move the residual score.
        r = self.client.post(f"/api/risks/{risk['id']}/controls", headers=headers, json={
            "control_id": control["id"],
        })
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["residual_score"], 9)

        r = self.client.patch(f"/api/controls/{control['id']}", headers=headers, json={
            "status": "effective",
            "mark_tested_now": True,
        })
        self.assertEqual(r.status_code, 200, r.text)
        self.assertIsNotNone(r.json()["last_tested_at"])

        r = self.client.get(f"/api/risks/{risk['id']}", headers=headers)
        self.assertEqual(r.status_code, 200, r.text)
        body = r.json()
        self.assertEqual(body["residual_score"], 4)
        self.assertEqual(body["residual_level"], "MEDIUM")
        self.assertEqual(body["effective_control_count"], 1)

    def test_invalid_likelihood_rejected(self):
        headers = self._register_and_login(f"rc3{self._n}@a.com", f"RC Org 3 {self._n}")

        r = self.client.post("/api/risks", headers=headers, json={
            "title": "Bad risk",
            "likelihood": "CATASTROPHIC",
        })
        self.assertEqual(r.status_code, 400)

    # -- linking -------------------------------------------------------

    def test_link_and_unlink_dataset_and_process(self):
        email = f"rc4{self._n}@a.com"
        headers = self._register_and_login(email, f"RC Org 4 {self._n}")
        self._headers_cache = {email: headers}
        dataset_id = self._create_bare_dataset(email)

        r = self.client.post("/api/business-processes", headers=headers, json={
            "name": f"Process {self._n}",
        })
        process_id = r.json()["id"]

        risk = self._create_risk(headers)

        r = self.client.post(f"/api/risks/{risk['id']}/datasets", headers=headers, json={
            "dataset_id": dataset_id,
        })
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(len(r.json()["linked_datasets"]), 1)
        self.assertEqual(r.json()["dataset_count"], 1)

        r = self.client.post(f"/api/risks/{risk['id']}/processes", headers=headers, json={
            "process_id": process_id,
        })
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(len(r.json()["linked_processes"]), 1)

        r = self.client.get(f"/api/risks/dataset/{dataset_id}", headers=headers)
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(len(r.json()), 1)
        self.assertEqual(r.json()[0]["id"], risk["id"])

        r = self.client.delete(f"/api/risks/{risk['id']}/datasets/{dataset_id}", headers=headers)
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["dataset_count"], 0)

    def test_duplicate_link_rejected(self):
        email = f"rc5{self._n}@a.com"
        headers = self._register_and_login(email, f"RC Org 5 {self._n}")
        self._headers_cache = {email: headers}
        dataset_id = self._create_bare_dataset(email)
        risk = self._create_risk(headers)

        r = self.client.post(f"/api/risks/{risk['id']}/datasets", headers=headers, json={
            "dataset_id": dataset_id,
        })
        self.assertEqual(r.status_code, 200, r.text)

        r = self.client.post(f"/api/risks/{risk['id']}/datasets", headers=headers, json={
            "dataset_id": dataset_id,
        })
        self.assertEqual(r.status_code, 400)

    # -- RBAC ------------------------------------------------------------

    def test_viewer_cannot_create_risk_or_control(self):
        admin_email = f"rc6a{self._n}@a.com"
        admin_headers = self._register_and_login(admin_email, f"RC Org 6 {self._n}")
        viewer_headers = self._invite(admin_headers, f"rc6v{self._n}@a.com", "viewer")

        r = self.client.post("/api/risks", headers=viewer_headers, json={"title": "Nope"})
        self.assertEqual(r.status_code, 403)

        r = self.client.post("/api/controls", headers=viewer_headers, json={"name": "Nope"})
        self.assertEqual(r.status_code, 403)

    def test_viewer_can_read_risks(self):
        admin_email = f"rc7a{self._n}@a.com"
        admin_headers = self._register_and_login(admin_email, f"RC Org 7 {self._n}")
        viewer_headers = self._invite(admin_headers, f"rc7v{self._n}@a.com", "viewer")

        self._create_risk(admin_headers)

        r = self.client.get("/api/risks", headers=viewer_headers)
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(len(r.json()), 1)

    # -- tenant scoping ----------------------------------------------

    def test_risks_are_tenant_scoped(self):
        headers_a = self._register_and_login(f"rc8a{self._n}@a.com", f"RC Org 8a {self._n}")
        headers_b = self._register_and_login(f"rc8b{self._n}@a.com", f"RC Org 8b {self._n}")

        risk = self._create_risk(headers_a)

        r = self.client.get("/api/risks", headers=headers_b)
        self.assertEqual(r.json(), [])

        r = self.client.get(f"/api/risks/{risk['id']}", headers=headers_b)
        self.assertEqual(r.status_code, 404)

    # -- maturity integration -----------------------------------------

    def test_maturity_risk_coverage_dimension(self):
        headers = self._register_and_login(f"rc9{self._n}@a.com", f"RC Org 9 {self._n}")
        dataset_id = self._create_high_sensitivity_dataset(headers)

        r = self.client.get(f"/api/governance/datasets/{dataset_id}/scorecard", headers=headers)
        self.assertEqual(r.json()["sensitivity_score"], "HIGH")

        r = self.client.get("/api/maturity", headers=headers)
        self.assertEqual(r.json()["coverage"]["pct_high_sensitivity_with_assessed_risk"], 0)

        # Close every other gap first so a risk assessment is the one
        # thing left uncovered - recommended_next_steps only surfaces
        # the 3 weakest dimensions, so with 4+ gaps tied at 0% this
        # one wouldn't make the cut otherwise.
        self.client.patch(f"/api/governance/datasets/{dataset_id}", headers=headers, json={
            "steward": "Alex",
            "purpose": "Customer support and order fulfillment",
        })
        r = self.client.post("/api/certification-requests", headers=headers, json={"dataset_id": dataset_id})
        self.client.post(f"/api/certification-requests/{r.json()['id']}/approve", headers=headers, json={})
        r = self.client.post("/api/data-contracts", headers=headers, json={
            "dataset_id": dataset_id,
            "schema_expectations": {"columns": [{"name": "id", "required": True}]},
        })
        self.client.post(f"/api/data-contracts/{r.json()['id']}/activate", headers=headers)

        r = self.client.get("/api/maturity", headers=headers)
        self.assertEqual(r.json()["coverage"]["pct_high_sensitivity_with_assessed_risk"], 0)
        joined = " ".join(r.json()["recommended_next_steps"])
        self.assertIn("risk assessment", joined.lower())

        risk = self._create_risk(headers)
        r = self.client.post(f"/api/risks/{risk['id']}/datasets", headers=headers, json={
            "dataset_id": dataset_id,
        })
        self.assertEqual(r.status_code, 200, r.text)

        r = self.client.get("/api/maturity", headers=headers)
        self.assertEqual(r.json()["coverage"]["pct_high_sensitivity_with_assessed_risk"], 100)

    # -- audit logging -------------------------------------------------

    def test_risk_and_control_actions_are_audit_logged(self):
        headers = self._register_and_login(f"rc10{self._n}@a.com", f"RC Org 10 {self._n}")

        risk = self._create_risk(headers)
        control = self._create_control(headers)
        self.client.post(f"/api/risks/{risk['id']}/controls", headers=headers, json={
            "control_id": control["id"],
        })

        r = self.client.get("/api/audit-log", headers=headers)
        actions = [entry["action"] for entry in r.json()]
        self.assertIn("risk.create", actions)
        self.assertIn("control.create", actions)
        self.assertIn("risk.link_control", actions)


if __name__ == "__main__":
    unittest.main()
