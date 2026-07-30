"""
Tests for "trace this dashboard" (app/services/dashboard_trace_service.py,
GET /api/ecosystem/trace/{dataset_id}) - the provenance explainer that
walks the real lineage graph hop by hop and produces a plain-English
narrative, falling back to a deterministic template whenever
ANTHROPIC_API_KEY isn't set (conftest.py pins it to "" for the whole
suite, same convention as test_embedding_service.py).
"""

import unittest
import uuid

from fastapi.testclient import TestClient

from app.db.database import SessionLocal
from app.main import app
from app.models.dataset import Dataset
from app.models.lineage import DatasetLineage
from app.models.organization import Organization
from app.models.source import DataSource


class DashboardTraceServiceTests(unittest.TestCase):

    def setUp(self):
        self._n = uuid.uuid4().hex[:8]
        self.db = SessionLocal()

    def tearDown(self):
        self.db.close()

    def _build_diamond(self):
        """
        raw1 \
              -> staging -> report
        raw2 /

        A genuine diamond: staging has two upstream parents, so a
        trace upstream from `report` must surface both raw1 and raw2
        at depth 2, and a trace downstream from either raw dataset
        must reach `report` at depth 2 without being visited twice.
        """
        org = Organization(name=f"Trace Org {self._n}", slug=self._n)
        self.db.add(org)
        self.db.flush()

        source = DataSource(name="Warehouse", type="postgresql", connection_config={}, organization_id=org.id)
        self.db.add(source)
        self.db.flush()

        raw1 = Dataset(name="orders_raw", schema_name="public", source_id=source.id, organization_id=org.id)
        raw2 = Dataset(name="customers_raw", schema_name="public", source_id=source.id, organization_id=org.id)
        staging = Dataset(name="dim_orders", schema_name="marts", source_id=source.id, organization_id=org.id)
        report = Dataset(name="Sales Dashboard", schema_name="tableau", source_id=source.id, organization_id=org.id)
        isolated = Dataset(name="orphan", schema_name="public", source_id=source.id, organization_id=org.id)
        self.db.add_all([raw1, raw2, staging, report, isolated])
        self.db.flush()

        self.db.add_all([
            DatasetLineage(upstream_dataset_id=raw1.id, downstream_dataset_id=staging.id, transformation_type="JOIN"),
            DatasetLineage(upstream_dataset_id=raw2.id, downstream_dataset_id=staging.id, transformation_type="JOIN"),
            DatasetLineage(upstream_dataset_id=staging.id, downstream_dataset_id=report.id, transformation_type="TABLEAU_WORKBOOK"),
        ])
        self.db.commit()

        return {"org": org, "raw1": raw1, "raw2": raw2, "staging": staging, "report": report, "isolated": isolated}

    def test_upstream_trace_surfaces_both_diamond_parents(self):
        from app.services.dashboard_trace_service import build_trace

        data = self._build_diamond()
        trace = build_trace(self.db, data["org"].id, data["report"].id, direction="upstream")

        self.assertEqual(trace["direction"], "upstream")
        depths = {level["depth"]: {d["id"] for d in level["datasets"]} for level in trace["levels"]}

        self.assertEqual(depths[0], {data["report"].id})
        self.assertEqual(depths[1], {data["staging"].id})
        self.assertEqual(depths[2], {data["raw1"].id, data["raw2"].id})
        self.assertNotIn(data["isolated"].id, {i for s in depths.values() for i in s})

    def test_downstream_trace_reaches_report_once(self):
        from app.services.dashboard_trace_service import build_trace

        data = self._build_diamond()
        trace = build_trace(self.db, data["org"].id, data["raw1"].id, direction="downstream")

        depths = {level["depth"]: {d["id"] for d in level["datasets"]} for level in trace["levels"]}
        self.assertEqual(depths[0], {data["raw1"].id})
        self.assertEqual(depths[1], {data["staging"].id})
        self.assertEqual(depths[2], {data["report"].id})

        # report shouldn't appear twice even though the diamond means
        # it's technically reachable more than once at deeper depths.
        all_ids = [d["id"] for level in trace["levels"] for d in level["datasets"]]
        self.assertEqual(len(all_ids), len(set(all_ids)))

    def test_isolated_dataset_has_no_lineage_and_says_so(self):
        from app.services.dashboard_trace_service import build_trace

        data = self._build_diamond()
        trace = build_trace(self.db, data["org"].id, data["isolated"].id, direction="upstream")

        self.assertEqual(len(trace["levels"]), 1)
        self.assertIn("no recorded", trace["narrative"].lower())

    def test_narrative_falls_back_to_template_without_api_key(self):
        from app.services.dashboard_trace_service import build_trace

        data = self._build_diamond()
        trace = build_trace(self.db, data["org"].id, data["report"].id, direction="upstream")

        self.assertEqual(trace["narrative_source"], "template")
        self.assertIn("Sales Dashboard", trace["narrative"])
        self.assertIn("2 hop", trace["narrative"])

    def test_unknown_dataset_raises(self):
        from app.services.dashboard_trace_service import build_trace, DatasetNotFoundError

        data = self._build_diamond()
        with self.assertRaises(DatasetNotFoundError):
            build_trace(self.db, data["org"].id, "not-a-real-id", direction="upstream")

    def test_trace_is_tenant_scoped(self):
        from app.services.dashboard_trace_service import build_trace, DatasetNotFoundError

        data = self._build_diamond()
        other_org = Organization(name=f"Other Org {self._n}", slug=f"other-{self._n}")
        self.db.add(other_org)
        self.db.commit()

        with self.assertRaises(DatasetNotFoundError):
            build_trace(self.db, other_org.id, data["report"].id, direction="upstream")


class DashboardTraceApiTests(unittest.TestCase):

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

    def test_trace_endpoint_on_seeded_org(self):
        headers = self._register_and_login(f"trace{self._n}@a.com", f"Trace Seed Org {self._n}")
        r = self.client.post("/api/demo/seed", headers=headers)
        self.assertEqual(r.status_code, 200, r.text)

        r = self.client.get("/api/ecosystem", headers=headers)
        datasets = r.json()["datasets"]
        back_office = next((d for d in datasets if d["tier"] == "BACK_OFFICE"), None)

        if back_office is None:
            self.skipTest("Seeded demo estate has no BACK_OFFICE dataset to trace in this snapshot.")

        r = self.client.get(f"/api/ecosystem/trace/{back_office['id']}", headers=headers)
        self.assertEqual(r.status_code, 200, r.text)
        body = r.json()
        self.assertIn("narrative", body)
        self.assertIn("levels", body)
        self.assertEqual(body["levels"][0]["datasets"][0]["id"], back_office["id"])

    def test_trace_endpoint_404_for_unknown_dataset(self):
        headers = self._register_and_login(f"trace404{self._n}@a.com", f"Trace 404 Org {self._n}")
        r = self.client.get("/api/ecosystem/trace/not-a-real-id", headers=headers)
        self.assertEqual(r.status_code, 404, r.text)

    def test_trace_endpoint_requires_auth(self):
        r = self.client.get("/api/ecosystem/trace/some-id")
        self.assertEqual(r.status_code, 401, r.text)

    def test_trace_endpoint_rejects_bad_direction(self):
        headers = self._register_and_login(f"tracebaddir{self._n}@a.com", f"Trace Bad Dir Org {self._n}")
        r = self.client.get("/api/ecosystem/trace/some-id", headers=headers, params={"direction": "sideways"})
        self.assertEqual(r.status_code, 422, r.text)


if __name__ == "__main__":
    unittest.main()
