"""
Tests for the NL Q&A assistant: the deterministic intent handlers
(PII exposure, ownership, lineage, governance/maturity, contract
health) each answered directly from real data, the semantic-search
fallback for anything else, tenant scoping, and the API endpoint.
"""

import os
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

    def _ask_with_history(self, headers, query, history):
        r = self.client.post(
            "/api/assistant/ask", headers=headers, json={"query": query, "history": history}
        )
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

    def test_followup_question_resolves_dataset_from_conversation_history(self):
        # Regression test: a real reported bug - the first answer names
        # a dataset ("public.customers"), and a follow-up that doesn't
        # repeat the name ("who owns it") "forgot" that subject entirely
        # and fell back to the generic no-dataset-named prompt, because
        # the deterministic ownership handler only ever looked at the
        # current message's text, never the conversation history it was
        # already being sent.
        headers = self._register_and_login(f"amem1{self._n}@a.com", f"Assistant Org Mem1 {self._n}")
        source_id = self._create_source(headers, f"SM1{self._n}")
        self._scan(headers, source_id, SCAN_RESULT)

        self.client.patch(
            f"/api/governance/datasets/{self.client.get('/api/datasets', headers=headers).json()[0]['id']}",
            headers=headers,
            json={"owner": "Priya"},
        )

        first = self._ask(headers, "which datasets have PII?")
        self.assertIn("customers", first["answer"])

        history = [
            {"role": "user", "text": "which datasets have PII?"},
            {"role": "assistant", "text": first["answer"]},
        ]
        second = self._ask_with_history(headers, "who owns it?", history)
        self.assertIn("Priya", second["answer"])
        self.assertNotIn("name a specific dataset", second["answer"])

    def test_followup_lineage_question_resolves_dataset_from_history(self):
        headers = self._register_and_login(f"amem2{self._n}@a.com", f"Assistant Org Mem2 {self._n}")
        source_id = self._create_source(headers, f"SM2{self._n}")
        self._scan(headers, source_id, SCAN_RESULT)
        self._scan(headers, source_id, ORDERS_SCAN_RESULT)

        datasets = self.client.get("/api/datasets", headers=headers).json()
        customers_id = next(d["id"] for d in datasets if d["name"] == "customers")
        orders_id = next(d["id"] for d in datasets if d["name"] == "orders")
        self.client.post("/api/lineage", headers=headers, json={
            "upstream_dataset_id": customers_id,
            "downstream_dataset_id": orders_id,
            "transformation_type": "join",
        })

        first = self._ask(headers, "who owns customers?")

        history = [
            {"role": "user", "text": "who owns customers?"},
            {"role": "assistant", "text": first["answer"]},
        ]
        second = self._ask_with_history(headers, "what's downstream of it?", history)
        self.assertIn("orders", second["answer"])
        self.assertNotIn("name a specific dataset or", second["answer"])

    def test_followup_quality_question_resolves_dataset_from_history(self):
        headers = self._register_and_login(f"amem3{self._n}@a.com", f"Assistant Org Mem3 {self._n}")
        source_id = self._create_source(headers, f"SM3{self._n}")
        self._scan(headers, source_id, ORDERS_SCAN_RESULT)

        first = self._ask(headers, "who owns orders?")

        history = [
            {"role": "user", "text": "who owns orders?"},
            {"role": "assistant", "text": first["answer"]},
        ]
        second = self._ask_with_history(headers, "what's its quality score?", history)
        self.assertIn("quality score", second["answer"])
        self.assertNotIn("Governance maturity:", second["answer"])

    def test_followup_glossary_question_scoped_to_conversation_dataset(self):
        # Regression test: a real reported bug - "what glossary terms
        # are associated" as a follow-up to "who owns customers?" came
        # back with a mix of relevant and irrelevant terms, because
        # there was no dedicated glossary handler at all - it fell
        # through to the unscoped semantic-search fallback, which
        # ranks the whole catalog against the raw query text instead of
        # "everything actually linked to this one dataset".
        headers = self._register_and_login(f"amem4{self._n}@a.com", f"Assistant Org Mem4 {self._n}")
        source_id = self._create_source(headers, f"SM4{self._n}")
        self._scan(headers, source_id, SCAN_RESULT)
        self._scan(headers, source_id, ORDERS_SCAN_RESULT)

        datasets = self.client.get("/api/datasets", headers=headers).json()
        customers_id = next(d["id"] for d in datasets if d["name"] == "customers")
        orders_id = next(d["id"] for d in datasets if d["name"] == "orders")

        linked_term_id = self.client.post("/api/governance/glossary", headers=headers, json={
            "term": "Customer Identifier",
            "definition": "The unique identifier for a customer record.",
        }).json()["id"]
        self.client.post("/api/glossary-links", headers=headers, json={
            "term_id": linked_term_id,
            "dataset_id": customers_id,
        })

        unrelated_term_id = self.client.post("/api/governance/glossary", headers=headers, json={
            "term": "Order Total",
            "definition": "The total monetary value of an order.",
        }).json()["id"]
        self.client.post("/api/glossary-links", headers=headers, json={
            "term_id": unrelated_term_id,
            "dataset_id": orders_id,
        })

        first = self._ask(headers, "who owns customers?")

        history = [
            {"role": "user", "text": "who owns customers?"},
            {"role": "assistant", "text": first["answer"]},
        ]
        second = self._ask_with_history(headers, "what glossary terms are associated?", history)
        self.assertIn("Customer Identifier", second["answer"])
        self.assertNotIn("Order Total", second["answer"])
        self.assertTrue(any(s["type"] == "glossary_term" for s in second["sources"]))

    def test_followup_process_question_scoped_to_conversation_dataset(self):
        headers = self._register_and_login(f"amem5{self._n}@a.com", f"Assistant Org Mem5 {self._n}")
        source_id = self._create_source(headers, f"SM5{self._n}")
        self._scan(headers, source_id, SCAN_RESULT)
        self._scan(headers, source_id, ORDERS_SCAN_RESULT)

        datasets = self.client.get("/api/datasets", headers=headers).json()
        customers_id = next(d["id"] for d in datasets if d["name"] == "customers")
        orders_id = next(d["id"] for d in datasets if d["name"] == "orders")

        process_id = self.client.post("/api/business-processes", headers=headers, json={
            "name": "Customer Onboarding",
        }).json()["id"]
        self.client.post(f"/api/business-processes/{process_id}/datasets", headers=headers, json={
            "dataset_id": customers_id,
        })

        other_process_id = self.client.post("/api/business-processes", headers=headers, json={
            "name": "Order Fulfillment",
        }).json()["id"]
        self.client.post(f"/api/business-processes/{other_process_id}/datasets", headers=headers, json={
            "dataset_id": orders_id,
        })

        first = self._ask(headers, "who owns customers?")

        history = [
            {"role": "user", "text": "who owns customers?"},
            {"role": "assistant", "text": first["answer"]},
        ]
        second = self._ask_with_history(headers, "which business process uses this?", history)
        self.assertIn("Customer Onboarding", second["answer"])
        self.assertNotIn("Order Fulfillment", second["answer"])

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

    def test_lineage_question_resolves_a_source_name_not_just_a_dataset_name(self):
        # No dataset is ever literally named "salesforce" - the tables
        # under a source are things like "customers"/"leads", grouped
        # by schema_name. A question naming the *system* ("Salesforce
        # CRM") rather than one of its tables has to resolve via the
        # source name (or shared schema), not a dataset-name substring
        # match, which is exactly what the old implementation required
        # and could never satisfy for a query like this.
        headers = self._register_and_login(f"a14{self._n}@a.com", f"Assistant Org 14 {self._n}")
        source_id = self._create_source(headers, "Salesforce CRM")
        self._scan(headers, source_id, SCAN_RESULT)

        other_source_id = self._create_source(headers, f"Warehouse{self._n}")
        self._scan(headers, other_source_id, ORDERS_SCAN_RESULT)

        datasets = self.client.get("/api/datasets", headers=headers).json()
        customers_id = next(d["id"] for d in datasets if d["name"] == "customers")
        orders_id = next(d["id"] for d in datasets if d["name"] == "orders")

        r = self.client.post("/api/lineage", headers=headers, json={
            "upstream_dataset_id": customers_id,
            "downstream_dataset_id": orders_id,
            "transformation_type": "join",
        })
        self.assertEqual(r.status_code, 200, r.text)

        body = self._ask(headers, "where is data from salesforceCRM flowing")
        self.assertIn("orders", body["answer"])

    def test_pii_flow_question_names_the_system_and_flags_downstream_pii(self):
        # The exact shape of question that used to be silently
        # mis-answered: it mentions both a system ("salesforceCRM")
        # and PII wording ("PII data") together with "flowing". Before
        # the fix, the PII intent (checked first) matched on "PII" and
        # returned the generic top-10-sensitivity list, completely
        # ignoring "salesforceCRM" and never touching lineage at all.
        headers = self._register_and_login(f"a15{self._n}@a.com", f"Assistant Org 15 {self._n}")
        source_id = self._create_source(headers, "Salesforce CRM")
        self._scan(headers, source_id, SCAN_RESULT)

        other_source_id = self._create_source(headers, f"Warehouse{self._n}")
        # Downstream also carries its own PII column (email), so the
        # PII-focused branch of the lineage answer has something to
        # flag.
        downstream_scan = {
            "datasets": [{
                "schema_name": "public", "table_name": "orders",
                "columns": [("id", "integer", "NO"), ("email", "text", "YES")],
                "row_count": 1,
                "column_stats": {
                    "id": {"non_null": 1, "distinct": 1},
                    "email": {"non_null": 1, "distinct": 1},
                },
                "column_samples": {"id": ["1"], "email": ["a@b.com"]},
            }],
            "foreign_keys": [],
        }
        self._scan(headers, other_source_id, downstream_scan)

        datasets = self.client.get("/api/datasets", headers=headers).json()
        customers_id = next(d["id"] for d in datasets if d["name"] == "customers")
        orders_id = next(d["id"] for d in datasets if d["name"] == "orders")

        r = self.client.post("/api/lineage", headers=headers, json={
            "upstream_dataset_id": customers_id,
            "downstream_dataset_id": orders_id,
            "transformation_type": "join",
        })
        self.assertEqual(r.status_code, 200, r.text)

        body = self._ask(headers, "where is salesforceCRM PII data flowing")

        # Went through the lineage handler (names the actual downstream
        # dataset and flags its PII), not the generic PII list, which
        # never mentions any specific system by name.
        self.assertIn("orders", body["answer"])
        self.assertNotIn("carry meaningful personal-data risk", body["answer"])
        self.assertIn("PII column", body["answer"])

    def test_governance_intent_reports_maturity_level(self):
        headers = self._register_and_login(f"a7{self._n}@a.com", f"Assistant Org 7 {self._n}")
        source_id = self._create_source(headers, f"S7{self._n}")
        self._scan(headers, source_id, ORDERS_SCAN_RESULT)

        body = self._ask(headers, "how's our governance maturity?")
        self.assertIn("Governance maturity:", body["answer"])

    def test_quality_intent_reports_score_not_governance_maturity(self):
        # Regression test: "quality score" used to live in
        # GOVERNANCE_KEYWORDS, so this question was silently answered
        # with org-wide governance maturity instead of the dataset's
        # actual profiled quality score.
        headers = self._register_and_login(f"aq1{self._n}@a.com", f"Assistant Org QA1 {self._n}")
        source_id = self._create_source(headers, f"SQ1{self._n}")
        self._scan(headers, source_id, ORDERS_SCAN_RESULT)

        body = self._ask(headers, "what's the quality score for orders?")
        self.assertIn("quality score", body["answer"])
        self.assertNotIn("Governance maturity:", body["answer"])

    def test_quality_intent_org_wide_summary_when_no_dataset_named(self):
        headers = self._register_and_login(f"aq2{self._n}@a.com", f"Assistant Org QA2 {self._n}")
        source_id = self._create_source(headers, f"SQ2{self._n}")
        self._scan(headers, source_id, ORDERS_SCAN_RESULT)

        body = self._ask(headers, "how's our data quality looking?")
        self.assertIn("quality profile", body["answer"])
        self.assertNotIn("Governance maturity:", body["answer"])

    def test_pii_intent_scoped_to_sources_lists_source_names(self):
        # Regression test: "which sources have PII" used to fall
        # through to the same dataset-level list as "which datasets
        # have PII", ignoring that the question was scoped to systems.
        headers = self._register_and_login(f"aq3{self._n}@a.com", f"Assistant Org QA3 {self._n}")
        source_name = f"SalesforceCRM{self._n}"
        source_id = self._create_source(headers, source_name)
        self._scan(headers, source_id, SCAN_RESULT)

        other_source_id = self._create_source(headers, f"CleanSource{self._n}")
        self._scan(headers, other_source_id, ORDERS_SCAN_RESULT)

        body = self._ask(headers, "which sources have PII?")
        self.assertIn(source_name, body["answer"])
        self.assertTrue(any(s["type"] == "source" for s in body["sources"]))
        self.assertNotIn("CleanSource", body["answer"])

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

    # -- LLM path (ANTHROPIC_API_KEY configured) --------------------------
    #
    # None of the tests above set ANTHROPIC_API_KEY, so they all keep
    # exercising the deterministic paths exactly as before - confirming
    # the LLM path is genuinely additive, not a replacement. These tests
    # mock the HTTP boundary (_call_anthropic_api) rather than making a
    # real network call, following the same style used for send_email in
    # test_magic_link_login.py.

    @patch("app.services.assistant_service._call_anthropic_api")
    def test_llm_path_not_invoked_without_api_key(self, mock_call):
        headers = self._register_and_login(f"allm0{self._n}@a.com", f"LLM Org 0 {self._n}")
        source_id = self._create_source(headers, f"SLLM0{self._n}")
        self._scan(headers, source_id, SCAN_RESULT)

        body = self._ask(headers, "which datasets have PII?")

        mock_call.assert_not_called()
        self.assertIn("customers", body["answer"])

    @patch("app.services.assistant_service._call_anthropic_api")
    def test_llm_path_used_when_api_key_configured(self, mock_call):
        mock_call.return_value = "The customers dataset holds contact details for each customer."

        headers = self._register_and_login(f"allm1{self._n}@a.com", f"LLM Org 1 {self._n}")
        source_id = self._create_source(headers, f"SLLM1{self._n}")
        self._scan(headers, source_id, SCAN_RESULT)

        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}):
            body = self._ask(headers, "tell me about the customers dataset")

        self.assertTrue(mock_call.called)
        self.assertEqual(
            body["answer"],
            "The customers dataset holds contact details for each customer.",
        )

    @patch("app.services.assistant_service._call_anthropic_api")
    def test_llm_path_falls_back_to_deterministic_on_api_failure(self, mock_call):
        # None simulates any failure inside _call_anthropic_api (network
        # error, timeout, non-200, unexpected response shape) - it always
        # collapses to None rather than raising.
        mock_call.return_value = None

        headers = self._register_and_login(f"allm2{self._n}@a.com", f"LLM Org 2 {self._n}")
        source_id = self._create_source(headers, f"SLLM2{self._n}")
        self._scan(headers, source_id, SCAN_RESULT)

        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}):
            body = self._ask(headers, "which datasets have PII?")

        self.assertTrue(mock_call.called)
        # Same deterministic PII answer as the no-key path.
        self.assertIn("customers", body["answer"])

    @patch("app.services.assistant_service._call_anthropic_api")
    def test_llm_path_forwards_conversation_history(self, mock_call):
        mock_call.return_value = "Yes, email and phone are both PII on that dataset."

        headers = self._register_and_login(f"allm3{self._n}@a.com", f"LLM Org 3 {self._n}")
        source_id = self._create_source(headers, f"SLLM3{self._n}")
        self._scan(headers, source_id, SCAN_RESULT)

        history = [
            {"role": "user", "text": "what does the customers dataset contain?"},
            {"role": "assistant", "text": "It has id, email, and phone columns."},
        ]

        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}):
            r = self.client.post("/api/assistant/ask", headers=headers, json={
                "query": "is any of that PII?",
                "history": history,
            })
        self.assertEqual(r.status_code, 200, r.text)

        self.assertTrue(mock_call.called)
        _, messages = mock_call.call_args.args
        self.assertEqual(
            messages[0],
            {"role": "user", "content": "what does the customers dataset contain?"},
        )
        self.assertEqual(
            messages[1],
            {"role": "assistant", "content": "It has id, email, and phone columns."},
        )
        self.assertEqual(messages[-1], {"role": "user", "content": "is any of that PII?"})


class FollowUpSuggestionTests(unittest.TestCase):
    """
    Every answer whose sources include a dataset should come back with
    follow_up_suggestions pointing at other things that dataset is
    connected to (glossary, process, contract, quality, risk, lineage,
    system, PII) - and should never re-suggest whatever angle the
    current question already covered.
    """

    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)

    def setUp(self):
        self._n = uuid.uuid4().hex[:8]

    def _register_and_login(self, email, org_name):
        r = self.client.post("/api/auth/register", json={
            "email": email, "password": "password123", "organization_name": org_name,
        })
        self.assertEqual(r.status_code, 200, r.text)
        r = self.client.post("/api/auth/login", json={"email": email, "password": "password123"})
        return {"Authorization": f"Bearer {r.json()['access_token']}"}

    def _create_source(self, headers, name):
        r = self.client.post("/api/sources", headers=headers, json={
            "name": name, "type": "postgresql",
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

    def test_ownership_answer_suggests_other_angles(self):
        headers = self._register_and_login(f"fu1{self._n}@a.com", f"FollowUp Org 1 {self._n}")
        source_id = self._create_source(headers, f"FU1{self._n}")
        self._scan(headers, source_id, SCAN_RESULT)

        body = self._ask(headers, "who owns customers?")

        suggestions = body["follow_up_suggestions"]
        self.assertTrue(len(suggestions) > 0)
        queries = " ".join(s["query"] for s in suggestions)
        self.assertIn("customers", queries)
        categories_offered = {s["label"] for s in suggestions}
        # Ownership isn't one of the suggestion categories itself, so
        # nothing should be suppressed - contract/quality/systems/pii
        # are always-on candidates.
        self.assertTrue(categories_offered & {"Data contract", "Data quality", "Source system", "PII"})

    def test_lineage_answer_does_not_resuggest_lineage(self):
        headers = self._register_and_login(f"fu2{self._n}@a.com", f"FollowUp Org 2 {self._n}")
        source_id = self._create_source(headers, f"FU2{self._n}")
        self._scan(headers, source_id, SCAN_RESULT)
        self._scan(headers, source_id, ORDERS_SCAN_RESULT)

        body = self._ask(headers, "what's downstream of customers?")

        suggestions = body["follow_up_suggestions"]
        self.assertTrue(len(suggestions) > 0)
        labels = {s["label"] for s in suggestions}
        self.assertNotIn("Lineage", labels)

    def test_pii_answer_does_not_resuggest_pii(self):
        headers = self._register_and_login(f"fu3{self._n}@a.com", f"FollowUp Org 3 {self._n}")
        source_id = self._create_source(headers, f"FU3{self._n}")
        self._scan(headers, source_id, SCAN_RESULT)

        # The PII intent's answer still carries the at-risk dataset(s)
        # as sources, so follow-ups are generated against the first one -
        # just without re-suggesting the PII angle itself.
        body = self._ask(headers, "which datasets have PII?")
        suggestions = body["follow_up_suggestions"]
        self.assertTrue(len(suggestions) > 0)
        labels = {s["label"] for s in suggestions}
        self.assertNotIn("PII", labels)

    def test_glossary_and_process_suggestions_only_appear_when_linked(self):
        headers = self._register_and_login(f"fu4{self._n}@a.com", f"FollowUp Org 4 {self._n}")
        source_id = self._create_source(headers, f"FU4{self._n}")
        self._scan(headers, source_id, SCAN_RESULT)

        dataset_id = self.client.get("/api/datasets", headers=headers).json()[0]["id"]

        body = self._ask(headers, "who owns customers?")
        labels_before = {s["label"] for s in body["follow_up_suggestions"]}
        self.assertNotIn("Glossary terms", labels_before)
        self.assertNotIn("Business process", labels_before)

        term_id = self.client.post("/api/governance/glossary", headers=headers, json={
            "term": f"CustomerTerm{self._n}", "definition": "A customer record",
        }).json()["id"]
        r = self.client.post("/api/glossary-links", headers=headers, json={
            "term_id": term_id, "dataset_id": dataset_id,
        })
        self.assertEqual(r.status_code, 200, r.text)

        body = self._ask(headers, "who owns customers?")
        labels_after = {s["label"] for s in body["follow_up_suggestions"]}
        self.assertIn("Glossary terms", labels_after)


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
