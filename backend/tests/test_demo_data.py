"""
Integration tests for the demo data feature (app/services/
demo_data_service.py + app/api/demo.py + app/api/column_lineage.py).
Seeds the full front-office -> processing -> reporting estate through
the real API, then checks every layer the narrative is supposed to
touch: source variety, dataset-level and column-level lineage across
all three layers, data quality contrast, contract compliance vs.
breach, all three governance outcomes, the certification queue, the
discussion thread, usage tracking, tenant scoping, role gating, and
that clearing removes exactly the seeded rows and nothing else.
"""

import unittest
import uuid

from fastapi.testclient import TestClient

from app.main import app


class DemoDataTests(unittest.TestCase):

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

    def _seed(self, headers):
        return self.client.post("/api/demo/seed", headers=headers)

    def _datasets_by_name(self, headers):
        r = self.client.get("/api/datasets", headers=headers)
        self.assertEqual(r.status_code, 200, r.text)
        return {d["name"]: d for d in r.json()}

    # -----------------------------------------------------------
    # Seeding: variety of applications, three layers, correct counts
    # -----------------------------------------------------------

    def test_seed_creates_sources_across_all_three_layers(self):
        headers = self._register_and_login(f"demo1{self._n}@a.com", f"Demo Org 1 {self._n}")

        r = self._seed(headers)
        self.assertEqual(r.status_code, 200, r.text)
        body = r.json()
        self.assertEqual(body["sources_created"], 5)
        self.assertEqual(body["datasets_created"], 15)

        r = self.client.get("/api/sources", headers=headers)
        sources = r.json()
        self.assertEqual(len(sources), 5)
        types = sorted(s["type"] for s in sources)
        self.assertEqual(types, ["dbt", "postgres", "salesforce", "tableau", "zendesk"])
        self.assertTrue(all(s["is_seed_data"] for s in sources))

    def test_seed_populates_front_office_processing_and_reporting_datasets(self):
        headers = self._register_and_login(f"demo2{self._n}@a.com", f"Demo Org 2 {self._n}")
        self._seed(headers)

        by_name = self._datasets_by_name(headers)

        # Front office (3 apps)
        for name in (
            "customers", "orders", "payments", "order_status_codes",
            "leads", "opportunities", "tickets",
        ):
            self.assertIn(name, by_name, f"missing front-office dataset {name}")

        # Data processing (dbt-modeled warehouse)
        for name in ("stg_customers", "stg_orders", "stg_payments", "dim_customers", "fct_customer_orders"):
            self.assertIn(name, by_name, f"missing processing-layer dataset {name}")

        # Reporting (Tableau)
        for name in ("Revenue Dashboard", "Customer 360", "Support SLA Report"):
            self.assertIn(name, by_name, f"missing reporting-layer dataset {name}")

    # -----------------------------------------------------------
    # Governance status variety
    # -----------------------------------------------------------

    def test_seed_produces_all_three_governance_outcomes(self):
        headers = self._register_and_login(f"demo3{self._n}@a.com", f"Demo Org 3 {self._n}")
        self._seed(headers)

        by_name = self._datasets_by_name(headers)

        self.assertEqual(by_name["customers"]["governance_status"], "HEALTHY")
        self.assertEqual(by_name["payments"]["governance_status"], "CRITICAL")
        self.assertEqual(by_name["tickets"]["governance_status"], "REVIEW_REQUIRED")

    def test_seed_produces_freshness_variety(self):
        headers = self._register_and_login(f"demo4{self._n}@a.com", f"Demo Org 4 {self._n}")
        self._seed(headers)

        by_name = self._datasets_by_name(headers)

        self.assertEqual(by_name["leads"]["freshness_status"], "STALE")
        self.assertEqual(by_name["tickets"]["freshness_status"], "AGING")
        self.assertEqual(by_name["customers"]["freshness_status"], "FRESH")

    # -----------------------------------------------------------
    # Data quality contrast
    # -----------------------------------------------------------

    def test_seed_produces_a_deliberately_poor_quality_table(self):
        headers = self._register_and_login(f"demo5{self._n}@a.com", f"Demo Org 5 {self._n}")
        self._seed(headers)

        by_name = self._datasets_by_name(headers)

        # payments' messy card_number/payment_method/billing sampling
        # should score meaningfully worse, in the *real* profiled data
        # quality record (completeness/validity/consistency computed
        # from the actual sample data), than customers' clean data -
        # not just Dataset.quality_score, which only reflects declared
        # schema nullability, not the sampled values themselves.
        r = self.client.get(
            f"/api/data-quality/dataset/{by_name['payments']['id']}", headers=headers
        )
        payments_quality = r.json()

        r = self.client.get(
            f"/api/data-quality/dataset/{by_name['customers']['id']}", headers=headers
        )
        customers_quality = r.json()

        self.assertLess(payments_quality["overall_score"], customers_quality["overall_score"])

    def test_seed_classifies_pii_and_financial_columns(self):
        headers = self._register_and_login(f"demo6{self._n}@a.com", f"Demo Org 6 {self._n}")
        self._seed(headers)

        by_name = self._datasets_by_name(headers)

        self.assertGreaterEqual(by_name["customers"]["pii_columns"], 2)
        self.assertEqual(by_name["payments"]["sensitivity_score"], "HIGH")

    # -----------------------------------------------------------
    # Dataset-level lineage across all three layers
    # -----------------------------------------------------------

    def test_seed_creates_multi_hop_lineage_across_layers(self):
        headers = self._register_and_login(f"demo7{self._n}@a.com", f"Demo Org 7 {self._n}")
        self._seed(headers)

        r = self.client.get("/api/lineage", headers=headers)
        edges = r.json()
        transformation_types = {e["transformation_type"] for e in edges}

        self.assertIn("ETL_INGESTION", transformation_types)
        self.assertIn("dbt_model", transformation_types)
        self.assertIn("TABLEAU_WORKBOOK", transformation_types)
        self.assertGreaterEqual(len(edges), 12)

        by_name = self._datasets_by_name(headers)
        fct_id = by_name["fct_customer_orders"]["id"]
        name_by_id = {d["id"]: name for name, d in by_name.items()}

        r = self.client.get(f"/api/lineage/{fct_id}/dependencies", headers=headers)
        upstream_names = {name_by_id[e["upstream_dataset_id"]] for e in r.json()}

        self.assertIn("stg_orders", upstream_names)
        self.assertIn("stg_payments", upstream_names)
        self.assertIn("stg_customers", upstream_names)

    def test_seed_creates_a_cross_application_merge_edge(self):
        """
        Salesforce leads feeding directly into the same staging model
        as the Postgres customers table - the "variety of
        applications, all connected" part of the story, not just three
        disconnected sources sitting side by side.
        """
        headers = self._register_and_login(f"demo8{self._n}@a.com", f"Demo Org 8 {self._n}")
        self._seed(headers)

        by_name = self._datasets_by_name(headers)
        leads_id = by_name["leads"]["id"]
        stg_customers_id = by_name["stg_customers"]["id"]

        r = self.client.get("/api/lineage", headers=headers)
        edges = r.json()
        match = [
            e for e in edges
            if e["upstream_dataset_id"] == leads_id and e["downstream_dataset_id"] == stg_customers_id
        ]
        self.assertEqual(len(match), 1)

    # -----------------------------------------------------------
    # Column-level lineage
    # -----------------------------------------------------------

    def test_seed_creates_column_level_lineage_including_a_masking_transform(self):
        headers = self._register_and_login(f"demo9{self._n}@a.com", f"Demo Org 9 {self._n}")
        self._seed(headers)

        by_name = self._datasets_by_name(headers)
        fct_id = by_name["fct_customer_orders"]["id"]

        r = self.client.get(f"/api/column-lineage/dataset/{fct_id}", headers=headers)
        self.assertEqual(r.status_code, 200, r.text)
        body = r.json()

        upstream_columns = {(e["downstream_column_name"], e["transformation_type"]) for e in body["upstream"]}
        self.assertIn(("masked_card_last4", "MASK"), upstream_columns)
        self.assertIn(("order_total", "CAST"), upstream_columns)
        self.assertIn(("customer_email", "PASSTHROUGH"), upstream_columns)

        downstream_columns = {(e["upstream_column_name"], e["transformation_type"]) for e in body["downstream"]}
        self.assertIn(("order_total", "AGGREGATION"), downstream_columns)

    def test_column_lineage_endpoint_404s_for_unknown_dataset(self):
        headers = self._register_and_login(f"demo10{self._n}@a.com", f"Demo Org 10 {self._n}")
        self._seed(headers)

        r = self.client.get("/api/column-lineage/dataset/does-not-exist", headers=headers)
        self.assertEqual(r.status_code, 404)

    # -----------------------------------------------------------
    # Contracts: one compliant, one breached
    # -----------------------------------------------------------

    def test_seed_creates_a_compliant_and_a_breached_contract(self):
        headers = self._register_and_login(f"demo11{self._n}@a.com", f"Demo Org 11 {self._n}")
        self._seed(headers)

        by_name = self._datasets_by_name(headers)

        self.assertEqual(by_name["fct_customer_orders"]["contract_status"], "COMPLIANT")
        self.assertEqual(by_name["payments"]["contract_status"], "BREACHED")

        r = self.client.get("/api/data-contracts", headers=headers, params={"dataset_id": by_name["payments"]["id"]})
        contracts = r.json()
        self.assertEqual(len(contracts), 1)
        self.assertIn("refund_status", contracts[0]["last_breach_details"])

    # -----------------------------------------------------------
    # Certification queue + discussion thread
    # -----------------------------------------------------------

    def test_seed_creates_a_pending_certification_request(self):
        headers = self._register_and_login(f"demo12{self._n}@a.com", f"Demo Org 12 {self._n}")
        self._seed(headers)

        by_name = self._datasets_by_name(headers)
        dim_customers_id = by_name["dim_customers"]["id"]

        r = self.client.get("/api/certification-requests", headers=headers, params={"status": "PENDING"})
        requests = r.json()
        match = [req for req in requests if req["dataset_id"] == dim_customers_id]
        self.assertEqual(len(match), 1)

    def test_seed_creates_a_discussion_thread_on_the_breached_dataset(self):
        headers = self._register_and_login(f"demo13{self._n}@a.com", f"Demo Org 13 {self._n}")
        self._seed(headers)

        by_name = self._datasets_by_name(headers)
        payments_id = by_name["payments"]["id"]

        r = self.client.get("/api/discussions", headers=headers, params={"dataset_id": payments_id})
        threads = r.json()
        self.assertEqual(len(threads), 1)
        self.assertEqual(threads[0]["status"], "OPEN")

    # -----------------------------------------------------------
    # Business Glossary <-> technical catalog links, and the
    # "process dimension" (business processes).
    # -----------------------------------------------------------

    def test_seed_links_glossary_terms_at_dataset_and_column_level(self):
        headers = self._register_and_login(f"demo21{self._n}@a.com", f"Demo Org 21 {self._n}")
        r = self._seed(headers)
        self.assertGreaterEqual(r.json()["glossary_terms_created"], 5)

        by_name = self._datasets_by_name(headers)

        # Dataset-level: "Customer" describes the whole customers table.
        r = self.client.get(f"/api/glossary-links/dataset/{by_name['customers']['id']}", headers=headers)
        links = r.json()
        customer_link = next(link for link in links if link["term"].startswith("Customer") and link["column_id"] is None)
        self.assertIsNone(customer_link["column_id"])

        # Column-level: "Customer Lifetime Value" pins to exactly one
        # column on dim_customers, not the whole table.
        r = self.client.get(f"/api/glossary-links/dataset/{by_name['dim_customers']['id']}", headers=headers)
        links = r.json()
        clv_link = next(link for link in links if link["term"] == "Customer Lifetime Value")
        self.assertEqual(clv_link["column_name"], "lifetime_value")

        # The masking transformation from the lineage story has a
        # matching business definition, not just a technical one.
        r = self.client.get(f"/api/glossary-links/dataset/{by_name['fct_customer_orders']['id']}", headers=headers)
        links = r.json()
        terms = {link["term"] for link in links}
        self.assertIn("Masked Card Number", terms)
        self.assertIn("Order Total", terms)

    def test_seed_creates_business_processes_spanning_all_three_layers(self):
        headers = self._register_and_login(f"demo22{self._n}@a.com", f"Demo Org 22 {self._n}")
        r = self._seed(headers)
        self.assertEqual(r.json()["business_processes_created"], 3)

        r = self.client.get("/api/business-processes", headers=headers)
        processes = {p["name"]: p for p in r.json()}
        self.assertIn("Order-to-Cash", processes)
        self.assertIn("Customer Onboarding", processes)
        self.assertIn("Customer Support", processes)

        by_name = self._datasets_by_name(headers)

        # Order-to-Cash spans front office (orders, payments), the
        # processing layer (stg_orders, stg_payments,
        # fct_customer_orders), and reporting (Revenue Dashboard).
        r = self.client.get(f"/api/business-processes/{processes['Order-to-Cash']['id']}/datasets", headers=headers)
        order_to_cash_datasets = {d["name"] for d in r.json()}
        self.assertIn("orders", order_to_cash_datasets)
        self.assertIn("fct_customer_orders", order_to_cash_datasets)
        self.assertIn("Revenue Dashboard", order_to_cash_datasets)

        # A single dataset can belong to more than one process -
        # Customer 360 supports both onboarding and support.
        r = self.client.get(f"/api/business-processes/dataset/{by_name['Customer 360']['id']}", headers=headers)
        dataset_processes = {p["name"] for p in r.json()}
        self.assertIn("Customer Onboarding", dataset_processes)
        self.assertIn("Customer Support", dataset_processes)

    def test_clear_removes_glossary_terms_and_processes_but_leaves_the_users_own(self):
        headers = self._register_and_login(f"demo23{self._n}@a.com", f"Demo Org 23 {self._n}")

        r = self.client.post("/api/governance/glossary", headers=headers, json={
            "term": f"My Own Term {self._n}",
            "definition": "Something this user defined themselves, unrelated to the demo.",
        })
        self.assertEqual(r.status_code, 200, r.text)
        own_term_id = r.json()["id"]

        r = self.client.post("/api/business-processes", headers=headers, json={
            "name": f"My Own Process {self._n}",
        })
        self.assertEqual(r.status_code, 200, r.text)
        own_process_id = r.json()["id"]

        self._seed(headers)

        r = self.client.post("/api/demo/clear", headers=headers)
        self.assertEqual(r.status_code, 200, r.text)
        body = r.json()
        self.assertEqual(body["glossary_terms_removed"], 5)
        self.assertEqual(body["business_processes_removed"], 3)

        r = self.client.get("/api/governance/glossary", headers=headers)
        remaining_terms = {t["id"] for t in r.json()}
        self.assertEqual(remaining_terms, {own_term_id})

        r = self.client.get("/api/business-processes", headers=headers)
        remaining_processes = {p["id"] for p in r.json()}
        self.assertEqual(remaining_processes, {own_process_id})

    # -----------------------------------------------------------
    # Usage tracking
    # -----------------------------------------------------------

    def test_seed_creates_view_history_for_popularity(self):
        headers = self._register_and_login(f"demo14{self._n}@a.com", f"Demo Org 14 {self._n}")
        self._seed(headers)

        by_name = self._datasets_by_name(headers)
        self.assertGreater(by_name["customers"]["view_count"], 0)
        self.assertGreater(by_name["Revenue Dashboard"]["view_count"], 0)

    # -----------------------------------------------------------
    # Idempotency / status / role gating / tenant scoping
    # -----------------------------------------------------------

    def test_seeding_twice_is_rejected(self):
        headers = self._register_and_login(f"demo15{self._n}@a.com", f"Demo Org 15 {self._n}")
        self._seed(headers)

        r = self._seed(headers)
        self.assertEqual(r.status_code, 400)

    def test_status_endpoint_reflects_seed_and_clear(self):
        headers = self._register_and_login(f"demo16{self._n}@a.com", f"Demo Org 16 {self._n}")

        r = self.client.get("/api/demo/status", headers=headers)
        self.assertEqual(r.json(), {"demo_data_loaded": False, "demo_source_count": 0})

        self._seed(headers)

        r = self.client.get("/api/demo/status", headers=headers)
        self.assertEqual(r.json(), {"demo_data_loaded": True, "demo_source_count": 5})

        r = self.client.post("/api/demo/clear", headers=headers)
        self.assertEqual(r.status_code, 200, r.text)

        r = self.client.get("/api/demo/status", headers=headers)
        self.assertEqual(r.json(), {"demo_data_loaded": False, "demo_source_count": 0})

    def test_clear_with_nothing_loaded_is_a_no_op(self):
        headers = self._register_and_login(f"demo17{self._n}@a.com", f"Demo Org 17 {self._n}")

        r = self.client.post("/api/demo/clear", headers=headers)
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["sources_removed"], 0)

    def test_clear_removes_demo_data_but_leaves_real_sources_and_datasets_untouched(self):
        headers = self._register_and_login(f"demo18{self._n}@a.com", f"Demo Org 18 {self._n}")

        real_source = self.client.post("/api/sources", headers=headers, json={
            "name": f"Real Prod Postgres {self._n}",
            "type": "postgres",
            "connection_config": {"host": "prod-db", "port": 5432, "database": "prod", "user": "svc"},
        })
        self.assertEqual(real_source.status_code, 200, real_source.text)

        self._seed(headers)

        r = self.client.post("/api/demo/clear", headers=headers)
        self.assertEqual(r.status_code, 200, r.text)
        body = r.json()
        self.assertEqual(body["sources_removed"], 5)
        self.assertEqual(body["datasets_removed"], 15)

        r = self.client.get("/api/sources", headers=headers)
        remaining = r.json()
        self.assertEqual(len(remaining), 1)
        self.assertEqual(remaining[0]["name"], f"Real Prod Postgres {self._n}")

        r = self.client.get("/api/datasets", headers=headers)
        self.assertEqual(r.json(), [])

        r = self.client.get("/api/lineage", headers=headers)
        self.assertEqual(r.json(), [])

    def test_seed_and_clear_require_admin_or_steward_role(self):
        headers = self._register_and_login(f"demo19{self._n}@a.com", f"Demo Org 19 {self._n}")

        r = self.client.post("/api/users", headers=headers, json={
            "email": f"demoviewer{self._n}@a.com",
            "password": "password123",
            "role": "viewer",
        })
        self.assertEqual(r.status_code, 200, r.text)

        r = self.client.post("/api/auth/login", json={
            "email": f"demoviewer{self._n}@a.com",
            "password": "password123",
        })
        viewer_headers = {"Authorization": f"Bearer {r.json()['access_token']}"}

        r = self.client.post("/api/demo/seed", headers=viewer_headers)
        self.assertEqual(r.status_code, 403)

        r = self.client.post("/api/demo/clear", headers=viewer_headers)
        self.assertEqual(r.status_code, 403)

    def test_tenant_scoping(self):
        headers_a = self._register_and_login(f"demo20a{self._n}@a.com", f"Demo Org 20a {self._n}")
        headers_b = self._register_and_login(f"demo20b{self._n}@a.com", f"Demo Org 20b {self._n}")

        self._seed(headers_a)

        r = self.client.get("/api/demo/status", headers=headers_b)
        self.assertEqual(r.json(), {"demo_data_loaded": False, "demo_source_count": 0})

        r = self.client.get("/api/datasets", headers=headers_b)
        self.assertEqual(r.json(), [])

        r = self.client.get("/api/sources", headers=headers_b)
        self.assertEqual(r.json(), [])

    # -----------------------------------------------------------
    # System of Record / System of Reference + data category
    # -----------------------------------------------------------

    def test_seed_tags_system_of_record_and_reference_pairs(self):
        headers = self._register_and_login(f"demo21{self._n}@a.com", f"Demo Org 21 {self._n}")
        self._seed(headers)

        by_name = self._datasets_by_name(headers)

        # customers/orders are where these entities are created - the
        # analytics-mart copies of the same entities are downstream,
        # derived reference copies, not the record of truth.
        self.assertEqual(by_name["customers"]["system_role"], "SYSTEM_OF_RECORD")
        self.assertEqual(by_name["orders"]["system_role"], "SYSTEM_OF_RECORD")
        self.assertEqual(by_name["dim_customers"]["system_role"], "SYSTEM_OF_REFERENCE")
        self.assertEqual(by_name["fct_customer_orders"]["system_role"], "SYSTEM_OF_REFERENCE")

        # Datasets nobody has explicitly tagged stay untagged rather
        # than defaulting to a guess - this is a steward call, not
        # something the seeder (or the app) should infer on its own.
        self.assertIsNone(by_name["payments"]["system_role"])

    def test_seed_datasets_get_auto_classified_data_category(self):
        headers = self._register_and_login(f"demo22{self._n}@a.com", f"Demo Org 22 {self._n}")
        self._seed(headers)

        by_name = self._datasets_by_name(headers)

        # Every dataset created via ingest_dataset_info() runs through
        # the naming heuristic at creation time - nothing should be
        # left unclassified.
        for name in (
            "customers", "orders", "payments", "order_status_codes",
            "leads", "opportunities", "tickets", "stg_customers",
            "stg_orders", "stg_payments", "dim_customers",
            "fct_customer_orders", "Revenue Dashboard", "Customer 360",
            "Support SLA Report",
        ):
            self.assertIsNotNone(
                by_name[name]["data_category"],
                f"{name} was not auto-classified",
            )

        self.assertEqual(by_name["customers"]["data_category"], "MASTER")
        self.assertEqual(by_name["orders"]["data_category"], "TRANSACTIONAL")
        self.assertEqual(by_name["order_status_codes"]["data_category"], "REFERENCE")
        self.assertEqual(by_name["fct_customer_orders"]["data_category"], "ANALYTICAL")
        self.assertEqual(by_name["Revenue Dashboard"]["data_category"], "ANALYTICAL")

    # -----------------------------------------------------------
    # Risk register + control library
    # -----------------------------------------------------------

    def test_seed_creates_risks_linked_to_datasets_processes_and_controls(self):
        headers = self._register_and_login(f"demo24{self._n}@a.com", f"Demo Org 24 {self._n}")
        r = self._seed(headers)
        self.assertEqual(r.json()["risks_created"], 3)
        self.assertEqual(r.json()["controls_created"], 3)

        r = self.client.get("/api/risks", headers=headers)
        self.assertEqual(r.status_code, 200, r.text)
        risks_by_title = {risk["title"]: risk for risk in r.json()}
        self.assertIn("Card data exposure via the payments table", risks_by_title)
        card_risk = risks_by_title["Card data exposure via the payments table"]
        self.assertEqual(card_risk["category"], "PRIVACY")
        self.assertEqual(card_risk["likelihood"], "HIGH")
        self.assertEqual(card_risk["status"], "OPEN")

        r = self.client.get(f"/api/risks/{card_risk['id']}", headers=headers)
        self.assertEqual(r.status_code, 200, r.text)
        detail = r.json()

        by_name = self._datasets_by_name(headers)
        linked_dataset_ids = {d["id"] for d in detail["linked_datasets"]}
        self.assertIn(by_name["payments"]["id"], linked_dataset_ids)

        linked_control_names = {c["name"] for c in detail["linked_controls"]}
        self.assertIn("PCI masking at the analytics layer", linked_control_names)
        self.assertIn("Quarterly access review for the payments schema", linked_control_names)

        r = self.client.get("/api/controls", headers=headers)
        self.assertEqual(r.status_code, 200, r.text)
        controls_by_name = {control["name"]: control for control in r.json()}
        self.assertEqual(controls_by_name["PCI masking at the analytics layer"]["status"], "EFFECTIVE")
        self.assertEqual(controls_by_name["PCI masking at the analytics layer"]["control_type"], "PREVENTIVE")

    def test_seed_masks_the_pci_relevant_column(self):
        headers = self._register_and_login(f"demo25{self._n}@a.com", f"Demo Org 25 {self._n}")
        self._seed(headers)

        by_name = self._datasets_by_name(headers)
        fct_id = by_name["fct_customer_orders"]["id"]

        r = self.client.get(f"/api/columns/dataset/{fct_id}", headers=headers)
        self.assertEqual(r.status_code, 200, r.text)
        columns_by_name = {c["name"]: c for c in r.json()}
        self.assertTrue(columns_by_name["masked_card_last4"]["masked"])

    # -----------------------------------------------------------
    # Privacy: retention, consent, purpose
    # -----------------------------------------------------------

    def test_seed_fills_privacy_fields_on_some_datasets_and_leaves_others_unassessed(self):
        headers = self._register_and_login(f"demo26{self._n}@a.com", f"Demo Org 26 {self._n}")
        self._seed(headers)

        r = self.client.get("/api/governance/scorecards", headers=headers)
        self.assertEqual(r.status_code, 200, r.text)
        by_name = {row["name"]: row for row in r.json()}

        self.assertEqual(by_name["customers"]["consent_status"], "CONSENT_OBTAINED")
        self.assertEqual(by_name["customers"]["retention_period_days"], 1825)

        self.assertEqual(by_name["payments"]["consent_status"], "CONSENT_NOT_REQUIRED")
        self.assertEqual(by_name["payments"]["retention_period_days"], 2555)

        # tickets is the deliberate gap - a real coverage story for the
        # Privacy Dashboard needs at least one dataset that hasn't been
        # assessed yet.
        self.assertEqual(by_name["tickets"]["consent_status"], "NOT_ASSESSED")
        self.assertIsNone(by_name["tickets"]["retention_period_days"])

    # -----------------------------------------------------------
    # All three discussion thread types
    # -----------------------------------------------------------

    def test_seed_creates_a_proposal_and_an_issue_thread(self):
        headers = self._register_and_login(f"demo27{self._n}@a.com", f"Demo Org 27 {self._n}")
        self._seed(headers)

        r = self.client.get("/api/discussions", headers=headers, params={"thread_type": "PROPOSAL"})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(len(r.json()), 1)

        r = self.client.get("/api/discussions", headers=headers, params={"thread_type": "ISSUE"})
        self.assertEqual(r.status_code, 200, r.text)
        issues = r.json()
        self.assertEqual(len(issues), 1)
        self.assertIsNotNone(issues[0]["raised_for_user_id"])

        r = self.client.get("/api/discussions", headers=headers, params={"thread_type": "QUESTION"})
        self.assertEqual(len(r.json()), 1)

    # -----------------------------------------------------------
    # Team roster
    # -----------------------------------------------------------

    def test_seed_adds_team_members_with_mixed_roles(self):
        headers = self._register_and_login(f"demo28{self._n}@a.com", f"Demo Org 28 {self._n}")
        r = self._seed(headers)
        self.assertEqual(r.json()["team_members_created"], 3)

        r = self.client.get("/api/users", headers=headers)
        self.assertEqual(r.status_code, 200, r.text)
        roles = sorted(member["role"] for member in r.json())
        # The registering admin plus the three seeded roles.
        self.assertEqual(roles, ["admin", "data_owner", "steward", "viewer"])
        self.assertTrue(all(member["is_active"] for member in r.json()))

    def test_clear_deactivates_seeded_team_members_rather_than_deleting_them(self):
        headers = self._register_and_login(f"demo29{self._n}@a.com", f"Demo Org 29 {self._n}")
        self._seed(headers)

        r = self.client.get("/api/users", headers=headers)
        before = {member["email"]: member for member in r.json()}
        seeded_emails = [email for email in before if "demo-datafe.example" in email]
        self.assertEqual(len(seeded_emails), 3)

        r = self.client.post("/api/demo/clear", headers=headers)
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["team_members_deactivated"], 3)

        r = self.client.get("/api/users", headers=headers)
        after = {member["email"]: member for member in r.json()}

        # Still present (not hard-deleted)...
        for email in seeded_emails:
            self.assertIn(email, after)
            # ...but no longer active.
            self.assertFalse(after[email]["is_active"])

        # The real admin who ran the seed/clear is untouched.
        self.assertTrue(after[f"demo29{self._n}@a.com"]["is_active"])

    def test_clear_removes_risks_and_controls(self):
        headers = self._register_and_login(f"demo30{self._n}@a.com", f"Demo Org 30 {self._n}")
        self._seed(headers)

        r = self.client.post("/api/demo/clear", headers=headers)
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["risks_removed"], 3)
        self.assertEqual(r.json()["controls_removed"], 3)

        r = self.client.get("/api/risks", headers=headers)
        self.assertEqual(r.json(), [])

        r = self.client.get("/api/controls", headers=headers)
        self.assertEqual(r.json(), [])

    # -----------------------------------------------------------
    # Query log
    # -----------------------------------------------------------

    def test_seed_logs_a_repeated_unanswered_query_for_the_search_insights_report(self):
        headers = self._register_and_login(f"demo31{self._n}@a.com", f"Demo Org 31 {self._n}")
        self._seed(headers)

        r = self.client.get("/api/query-log/report", headers=headers)
        self.assertEqual(r.status_code, 200, r.text)
        report = r.json()

        self.assertGreaterEqual(report["total_queries"], 9)
        self.assertGreaterEqual(report["unanswered_count"], 4)

        top = report["top_unanswered"][0]
        self.assertEqual(top["query_text"], "does the shipments dataset have an owner?")
        self.assertEqual(top["count"], 3)


if __name__ == "__main__":
    unittest.main()
