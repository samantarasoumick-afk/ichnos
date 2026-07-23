"""
Tests for the NL Q&A assistant: the deterministic intent handlers
(PII exposure, ownership, lineage, governance/maturity, contract
health) each answered directly from real data, the semantic-search
fallback for anything else, tenant scoping, and the API endpoint.
"""

import unittest
import uuid
from unittest.mock import patch, MagicMock

from fastapi.testclient import TestClient

from app.main import app
from app.services.catalog_search_service import semantic_search
from app.db.database import SessionLocal


SCAN_RESULT = {
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

ORDERS_SCAN_RESULT = {
    "datasets": [{
        "schema_name": "public",
        "table_name": "orders",
        "columns": [("id", "integer", "NO")],
        "row_count": 1,
        "column_stats": {"id": {"non_null": 1, "distinct": 1}},
        "column_samples": {"id": ["1"]},
    }],
    "foreign_keys": [],
}


class AssistantTests(unittest.TestCase):

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

    def _create_source(self, headers, name):
        r = self.client.post("/api/sources", headers=headers, json={
            "name": name,
            "type": "postgresql",
            "connection_config": {"host": "x", "database": "y", "user": "z", "password": "p"},
        })
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()["id"]

    @patch("app.api.scanner.get_scanner")
    def _scan(self, headers, source_id, scan_result, mock_get_scanner):
        mock_get_scanner.return_value = MagicMock(return_value=scan_result)
        r = self.client.post(f"/api/scanner/{source_id}", headers=headers)
        self.assertEqual(r.status_code, 200, r.text)

    def _ask(self, headers, query):
        r = self.client.post("/api/assistant/ask", headers=headers, json={"query": query})
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()

    def test_empty_catalog_says_so(self):
        headers = self._register_and_login(f"a1{self._n}@a.com", f"Assistant Org 1 {self._n}")
        body = self._ask(headers, "what datasets do we have")
        self.assertIn("nothing in your catalog", body["answer"])

    def test_pii_intent_lists_at_risk_datasets(self):
        headers = self._register_and_login(f"a2{self._n}@a.com", f"Assistant Org 2 {self._n}")
        source_id = self._create_source(headers, f"S2{self._n}")
        self._scan(headers, source_id, SCAN_RESULT)

        body = self._ask(headers, "which datasets have PII?")
        self.assertIn("customers", body["answer"])
        self.assertTrue(len(body["sources"]) >= 1)

    def test_pii_intent_reports_none_when_clean(self):
        headers = self._register_and_login(f"a3{self._n}@a.com", f"Assistant Org 3 {self._n}")
        source_id = self._create_source(headers, f"S3{self._n}")
        self._scan(headers, source_id, ORDERS_SCAN_RESULT)

        body = self._ask(headers, "any sensitive data here?")
        self.assertIn("None", body["answer"])

    def test_ownership_intent_reports_owner_and_steward(self):
        headers = self._register_and_login(f"a4{self._n}@a.com", f"Assistant Org 4 {self._n}")
        source_id = self._create_source(headers, f"S4{self._n}")
        self._scan(headers, source_id, SCAN_RESULT)

        dataset_id = self.client.get("/api/datasets", headers=headers).json()[0]["id"]
        self.client.patch(f"/api/governance/datasets/{dataset_id}", headers=headers, json={
            "owner": "Priya",
        })

        body = self._ask(headers, "who owns customers?")
        self.assertIn("Priya", body["answer"])

    def test_ownership_intent_without_named_dataset_prompts_for_one(self):
        headers = self._register_and_login(f"a5{self._n}@a.com", f"Assistant Org 5 {self._n}")
        source_id = self._create_source(headers, f"S5{self._n}")
        self._scan(headers, source_id, SCAN_RESULT)

        body = self._ask(headers, "who owns this")
        self.assertIn("name a specific dataset", body["answer"])

    def test_lineage_intent_reports_downstream(self):
        headers = self._register_and_login(f"a6{self._n}@a.com", f"Assistant Org 6 {self._n}")
        source_id = self._create_source(headers, f"S6{self._n}")
        self._scan(headers, source_id, SCAN_RESULT)
        self._scan(headers, source_id, ORDERS_SCAN_RESULT)

        datasets = self.client.get("/api/datasets", headers=headers).json()
        customers_id = next(d["id"] for d in datasets if d["name"] == "customers")
        orders_id = next(d["id"] for d in datasets if d["name"] == "orders")

        r = self.client.post("/api/lineage", headers=headers, json={
            "upstream_dataset_id": customers_id,
            "downstream_dataset_id": orders_id,
            "transformation_type": "join",
        })
        self.assertEqual(r.status_code, 200, r.text)

        body = self._ask(headers, "what's downstream of customers?")
        self.assertIn("orders", body["answer"])

    def test_governance_intent_reports_maturity_level(self):
        headers = self._register_and_login(f"a7{self._n}@a.com", f"Assistant Org 7 {self._n}")
        source_id = self._create_source(headers, f"S7{self._n}")
        self._scan(headers, source_id, ORDERS_SCAN_RESULT)

        body = self._ask(headers, "how's our governance maturity?")
        self.assertIn("Governance maturity:", body["answer"])

    def test_contract_intent_reports_no_contracts_initially(self):
        headers = self._register_and_login(f"a8{self._n}@a.com", f"Assistant Org 8 {self._n}")
        source_id = self._create_source(headers, f"S8{self._n}")
        self._scan(headers, source_id, ORDERS_SCAN_RESULT)

        body = self._ask(headers, "do we have any contract breaches?")
        self.assertIn("No datasets have an active data contract", body["answer"])

    def test_contract_intent_reports_breach(self):
        headers = self._register_and_login(f"a9{self._n}@a.com", f"Assistant Org 9 {self._n}")
        source_id = self._create_source(headers, f"S9{self._n}")
        self._scan(headers, source_id, SCAN_RESULT)

        dataset_id = self.client.get("/api/datasets", headers=headers).json()[0]["id"]

        r = self.client.post("/api/data-contracts", headers=headers, json={
            "dataset_id": dataset_id,
            "schema_expectations": {"columns": [{"name": "phone", "required": True}]},
        })
        contract_id = r.json()["id"]
        self.client.post(f"/api/data-contracts/{contract_id}/activate", headers=headers)

        # Rescan without "phone" -> breach.
        no_phone_scan = {
            "datasets": [{
                "schema_name": "public", "table_name": "customers",
                "columns": [("id", "integer", "NO")],
                "row_count": 1,
                "column_stats": {"id": {"non_null": 1, "distinct": 1}},
                "column_samples": {"id": ["1"]},
            }],
            "foreign_keys": [],
        }
        self._scan(headers, source_id, no_phone_scan)

        body = self._ask(headers, "are there any contract breaches?")
        self.assertIn("breached contract", body["answer"])

    def test_fallback_semantic_search_matches_glossary_term(self):
        headers = self._register_and_login(f"a10{self._n}@a.com", f"Assistant Org 10 {self._n}")
        source_id = self._create_source(headers, f"S10{self._n}")
        self._scan(headers, source_id, ORDERS_SCAN_RESULT)

        r = self.client.post("/api/governance/glossary", headers=headers, json={
            "term": "Churn Rate",
            "definition": "The percentage of customers who stop using the product in a given period.",
        })
        self.assertEqual(r.status_code, 200, r.text)

        body = self._ask(headers, "what does churn rate mean")
        self.assertIn("Churn Rate", body["answer"])
        self.assertTrue(any(s["type"] == "glossary_term" for s in body["sources"]))

    def test_no_match_says_so(self):
        headers = self._register_and_login(f"a11{self._n}@a.com", f"Assistant Org 11 {self._n}")
        source_id = self._create_source(headers, f"S11{self._n}")
        self._scan(headers, source_id, ORDERS_SCAN_RESULT)

        body = self._ask(headers, "xyzzyxyzzyxyzzy nonsense query zzz qux")
        self.assertIn("couldn't find anything", body["answer"])

    def test_empty_query_rejected(self):
        headers = self._register_and_login(f"a12{self._n}@a.com", f"Assistant Org 12 {self._n}")
        r = self.client.post("/api/assistant/ask", headers=headers, json={"query": "   "})
        self.assertEqual(r.status_code, 400)

    def test_answers_are_tenant_scoped(self):
        headers_a = self._register_and_login(f"a13a{self._n}@a.com", f"Assistant Org 13a {self._n}")
        headers_b = self._register_and_login(f"a13b{self._n}@a.com", f"Assistant Org 13b {self._n}")

        source_id = self._create_source(headers_a, f"S13{self._n}")
        self._scan(headers_a, source_id, SCAN_RESULT)

        body = self._ask(headers_b, "which datasets have PII?")
        self.assertIn("nothing in your catalog", body["answer"])


class SemanticSearchServiceTests(unittest.TestCase):
    """Direct unit tests of the retrieval layer, independent of the API."""

    def test_semantic_search_ranks_relevant_dataset_first(self):
        from app.models.organization import Organization
        from app.models.dataset import Dataset
        from app.models.source import DataSource

        db = SessionLocal()
        try:
            org = Organization(name=f"SemSearch Org {uuid.uuid4().hex[:8]}", slug=uuid.uuid4().hex[:8])
            db.add(org)
            db.flush()

            source = DataSource(name="src", type="postgresql", connection_config={}, organization_id=org.id)
            db.add(source)
            db.flush()

            relevant = Dataset(
                name="customer_transactions", schema_name="public",
                description="Financial transaction records for customer purchases",
                source_id=source.id, organization_id=org.id,
            )
            irrelevant = Dataset(
                name="server_logs", schema_name="public",
                description="Raw web server access logs",
                source_id=source.id, organization_id=org.id,
            )
            db.add_all([relevant, irrelevant])
            db.commit()

            results = semantic_search(db, org.id, "customer financial transaction data", top_k=5)

            self.assertTrue(len(results) >= 1)
            self.assertEqual(results[0].document.id, relevant.id)

        finally:
            db.close()


if __name__ == "__main__":
    unittest.main()
