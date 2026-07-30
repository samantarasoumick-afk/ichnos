"""
Tests for the Ecosystem View backend (app/services/ecosystem_service.py,
GET /api/ecosystem) - the new-analyst-onboarding map of an
organization's whole data estate, tiered into front/middle/back office
purely from real DatasetLineage topology (not a stored/tagged field).
"""

import unittest
import uuid

from fastapi.testclient import TestClient

from app.db.database import SessionLocal
from app.main import app
from app.models.column import DatasetColumn
from app.models.dataset import Dataset
from app.models.lineage import DatasetLineage
from app.models.organization import Organization
from app.models.source import DataSource


class EcosystemServiceTests(unittest.TestCase):
    """Direct service-level tests against a hand-built lineage chain,
    so tier assertions are exact rather than dependent on the shape of
    the full demo seeder."""

    def setUp(self):
        self._n = uuid.uuid4().hex[:8]
        self.db = SessionLocal()

    def tearDown(self):
        self.db.close()

    def _build_org_with_chain(self):
        """
        source_a: raw (front office, no upstream)
                     -> staging (middle office, in source_b)
                          -> report (back office, in source_c)
        plus a standalone dataset in source_a with no lineage at all.
        """
        org = Organization(name=f"Ecosystem Org {self._n}", slug=self._n)
        self.db.add(org)
        self.db.flush()

        source_a = DataSource(name="Storefront Postgres", type="postgresql", connection_config={}, organization_id=org.id)
        source_b = DataSource(name="Analytics Warehouse", type="dbt", connection_config={}, organization_id=org.id)
        source_c = DataSource(name="Tableau", type="tableau", connection_config={}, organization_id=org.id)
        self.db.add_all([source_a, source_b, source_c])
        self.db.flush()

        raw = Dataset(name="customers", schema_name="public", source_id=source_a.id, organization_id=org.id)
        staging = Dataset(name="dim_customers", schema_name="analytics_marts", source_id=source_b.id, organization_id=org.id)
        report = Dataset(name="Customer 360", schema_name="tableau", source_id=source_c.id, organization_id=org.id)
        standalone = Dataset(name="orphan_export", schema_name="public", source_id=source_a.id, organization_id=org.id)
        self.db.add_all([raw, staging, report, standalone])
        self.db.flush()

        self.db.add_all([
            DatasetColumn(dataset_id=raw.id, name="email", classification="PII"),
            DatasetColumn(dataset_id=raw.id, name="customer_id", classification="NONE"),
            DatasetColumn(dataset_id=staging.id, name="email", classification="PII"),
        ])

        self.db.add(DatasetLineage(upstream_dataset_id=raw.id, downstream_dataset_id=staging.id, transformation_type="ETL_INGESTION"))
        self.db.add(DatasetLineage(upstream_dataset_id=staging.id, downstream_dataset_id=report.id, transformation_type="TABLEAU_WORKBOOK"))
        self.db.commit()

        return {
            "org": org, "source_a": source_a, "source_b": source_b, "source_c": source_c,
            "raw": raw, "staging": staging, "report": report, "standalone": standalone,
        }

    def test_tiers_computed_from_lineage_topology(self):
        from app.services.ecosystem_service import build_ecosystem_graph

        data = self._build_org_with_chain()
        graph = build_ecosystem_graph(self.db, data["org"].id)

        tiers_by_id = {d["id"]: d["tier"] for d in graph["datasets"]}
        self.assertEqual(tiers_by_id[data["raw"].id], "FRONT_OFFICE")
        self.assertEqual(tiers_by_id[data["staging"].id], "MIDDLE_OFFICE")
        self.assertEqual(tiers_by_id[data["report"].id], "BACK_OFFICE")
        self.assertEqual(tiers_by_id[data["standalone"].id], "STANDALONE")

    def test_source_rollup_counts_and_tier(self):
        from app.services.ecosystem_service import build_ecosystem_graph

        data = self._build_org_with_chain()
        graph = build_ecosystem_graph(self.db, data["org"].id)

        sources_by_id = {s["id"]: s for s in graph["sources"]}
        source_a_node = sources_by_id[data["source_a"].id]

        # source_a has "customers" (front office) and "orphan_export"
        # (standalone) - a genuinely mixed source.
        self.assertEqual(source_a_node["dataset_count"], 2)
        self.assertEqual(source_a_node["total_columns"], 2)
        self.assertEqual(source_a_node["pii_columns"], 1)
        self.assertEqual(source_a_node["tier"], "FRONT_OFFICE")  # standalone excluded from tier voting

        source_b_node = sources_by_id[data["source_b"].id]
        self.assertEqual(source_b_node["tier"], "MIDDLE_OFFICE")
        self.assertEqual(source_b_node["dataset_count"], 1)

        source_c_node = sources_by_id[data["source_c"].id]
        self.assertEqual(source_c_node["tier"], "BACK_OFFICE")

    def test_source_edges_rolled_up_and_deduplicated(self):
        from app.services.ecosystem_service import build_ecosystem_graph

        data = self._build_org_with_chain()
        graph = build_ecosystem_graph(self.db, data["org"].id)

        pairs = {(e["upstream_source_id"], e["downstream_source_id"]) for e in graph["source_edges"]}
        self.assertIn((data["source_a"].id, data["source_b"].id), pairs)
        self.assertIn((data["source_b"].id, data["source_c"].id), pairs)
        # No edge within the same source (there isn't one here, but
        # guards against a same-source edge ever being mis-rolled-up).
        self.assertNotIn((data["source_a"].id, data["source_a"].id), pairs)

    def test_dataset_detail_fields_present(self):
        from app.services.ecosystem_service import build_ecosystem_graph

        data = self._build_org_with_chain()
        graph = build_ecosystem_graph(self.db, data["org"].id)

        raw_node = next(d for d in graph["datasets"] if d["id"] == data["raw"].id)
        for field in (
            "governance_status", "quality_score", "sensitivity_score", "contract_status",
            "purpose", "consent_status", "retention_status", "privacy_score",
        ):
            self.assertIn(field, raw_node)


class EcosystemApiTests(unittest.TestCase):

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

    def test_endpoint_returns_empty_shape_for_a_fresh_org(self):
        headers = self._register_and_login(f"eco{self._n}@a.com", f"Eco Org {self._n}")
        r = self.client.get("/api/ecosystem", headers=headers)
        self.assertEqual(r.status_code, 200, r.text)
        body = r.json()
        self.assertEqual(body["sources"], [])
        self.assertEqual(body["datasets"], [])
        self.assertEqual(body["edges"], [])

    def test_endpoint_requires_auth(self):
        r = self.client.get("/api/ecosystem")
        self.assertEqual(r.status_code, 401, r.text)

    def test_endpoint_is_tenant_scoped(self):
        headers_a = self._register_and_login(f"ecoa{self._n}@a.com", f"Eco Tenant A {self._n}")
        self.client.post("/api/demo/seed", headers=headers_a)

        headers_b = self._register_and_login(f"ecob{self._n}@a.com", f"Eco Tenant B {self._n}")
        r = self.client.get("/api/ecosystem", headers=headers_b)
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["sources"], [])

    def test_endpoint_reflects_full_bulk_seed(self):
        headers = self._register_and_login(f"ecoseed{self._n}@a.com", f"Eco Seed Org {self._n}")
        r = self.client.post("/api/demo/seed", headers=headers)
        self.assertEqual(r.status_code, 200, r.text)

        r = self.client.get("/api/ecosystem", headers=headers)
        self.assertEqual(r.status_code, 200, r.text)
        body = r.json()

        self.assertGreater(len(body["sources"]), 0)
        self.assertGreater(len(body["datasets"]), 0)
        self.assertGreater(len(body["edges"]), 0)

        tiers = {d["tier"] for d in body["datasets"]}
        # A real, multi-layer seeded estate should exercise all three
        # real tiers (front office sources, dbt processing, Tableau
        # reports all exist in the demo estate).
        self.assertTrue({"FRONT_OFFICE", "MIDDLE_OFFICE", "BACK_OFFICE"}.issubset(tiers))


if __name__ == "__main__":
    unittest.main()
