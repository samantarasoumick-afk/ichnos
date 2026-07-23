"""
Tests for the DQ + Lineage integration: a dataset's "effective" quality
score can be lifted (or pulled down) from what it inherits via upstream
lineage, depending on how well each connecting edge documents its
transformation and filter logic.

Product example this is built to reproduce exactly: a source with
overall_score=50 feeding a downstream dataset through a fully-documented
edge (transformation_type + a real transformation_description + real
filter_logic) lifts that downstream dataset to an effective score of 55.
"""

import types
import unittest
import uuid

from fastapi.testclient import TestClient

from app.main import app
from app.db.database import SessionLocal
from app.models.data_quality import DataQuality
from app.services.lineage_quality_service import documentation_completeness


def _scan_result(table_name):
    return {
        "datasets": [{
            "schema_name": "public",
            "table_name": table_name,
            "columns": [
                ("id", "integer", "NO"),
                ("value", "text", "YES"),
            ],
            "row_count": 2,
            "column_stats": {
                "id": {"non_null": 2, "distinct": 2},
                "value": {"non_null": 2, "distinct": 2},
            },
            "column_samples": {
                "id": ["1", "2"],
                "value": ["a", "b"],
            },
        }],
        "foreign_keys": [],
    }


class LineageQualityTests(unittest.TestCase):

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

    def _scan_dataset(self, headers, table_name):
        from unittest.mock import patch

        r = self.client.post("/api/sources", headers=headers, json={
            "name": f"Source {table_name} {self._n}",
            "type": "postgresql",
            "connection_config": {"host": "x"},
        })
        source_id = r.json()["id"]

        with patch("app.api.scanner.get_scanner", return_value=lambda config: _scan_result(table_name)):
            r = self.client.post(f"/api/scanner/{source_id}", headers=headers)
        self.assertEqual(r.status_code, 200, r.text)

        r = self.client.get("/api/datasets", headers=headers)
        matches = [d for d in r.json() if d["name"] == table_name]
        self.assertEqual(len(matches), 1, r.text)
        return matches[0]["id"]

    def _set_quality_score(self, dataset_id, score):
        db = SessionLocal()
        try:
            record = db.query(DataQuality).filter(DataQuality.dataset_id == dataset_id).first()
            record.overall_score = score
            db.commit()
        finally:
            db.close()

    def _clear_quality_profile(self, dataset_id):
        db = SessionLocal()
        try:
            db.query(DataQuality).filter(DataQuality.dataset_id == dataset_id).delete()
            db.commit()
        finally:
            db.close()

    def _create_edge(self, headers, upstream_id, downstream_id, **fields):
        payload = {
            "upstream_dataset_id": upstream_id,
            "downstream_dataset_id": downstream_id,
            **fields,
        }
        r = self.client.post("/api/lineage", headers=headers, json=payload)
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()

    def _get_effective(self, headers, dataset_id):
        r = self.client.get(f"/api/data-quality/dataset/{dataset_id}/effective", headers=headers)
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()

    # -- pure function: documentation_completeness weighting ------------

    def test_documentation_completeness_weighting(self):
        def edge(transformation_type=None, transformation_description=None, filter_logic=None):
            return types.SimpleNamespace(
                transformation_type=transformation_type,
                transformation_description=transformation_description,
                filter_logic=filter_logic,
            )

        self.assertEqual(documentation_completeness(edge()), 0.0)
        self.assertEqual(documentation_completeness(edge(transformation_type="SQL")), 0.4)
        self.assertEqual(
            documentation_completeness(edge(
                transformation_type="SQL",
                transformation_description="Joins orders to customers on customer_id.",
                filter_logic="WHERE status = 'active' AND deleted_at IS NULL",
            )),
            1.0,
        )
        # A short/token description or filter shouldn't count as substantive.
        self.assertEqual(
            documentation_completeness(edge(
                transformation_type="SQL",
                transformation_description="n/a",
                filter_logic="none",
            )),
            0.4,
        )

    # -- API: the exact product example ----------------------------------

    def test_fully_documented_edge_lifts_unprofiled_downstream_to_55(self):
        headers = self._register_and_login(f"full{self._n}@a.com", f"Full Org {self._n}")

        source_id = self._scan_dataset(headers, f"source_{self._n}")
        downstream_id = self._scan_dataset(headers, f"downstream_{self._n}")

        self._set_quality_score(source_id, 50.0)
        self._clear_quality_profile(downstream_id)

        self._create_edge(
            headers, source_id, downstream_id,
            transformation_type="SQL_TRANSFORM",
            transformation_description="Aggregates daily orders into a summary table.",
            filter_logic="WHERE order_status = 'completed'",
        )

        result = self._get_effective(headers, downstream_id)

        self.assertIsNone(result["own_score"])
        self.assertEqual(result["effective_score"], 55.0)
        self.assertEqual(len(result["contributing_edges"]), 1)
        contributing = result["contributing_edges"][0]
        self.assertEqual(contributing["documentation_completeness"], 100)
        self.assertEqual(contributing["adjustment"], 5.0)
        self.assertEqual(contributing["upstream_effective_score"], 50.0)

    def test_undocumented_edge_pulls_score_down(self):
        headers = self._register_and_login(f"undoc{self._n}@a.com", f"Undoc Org {self._n}")

        source_id = self._scan_dataset(headers, f"source_{self._n}")
        downstream_id = self._scan_dataset(headers, f"downstream_{self._n}")

        self._set_quality_score(source_id, 50.0)
        self._clear_quality_profile(downstream_id)

        self._create_edge(headers, source_id, downstream_id)

        result = self._get_effective(headers, downstream_id)

        self.assertEqual(result["effective_score"], 45.0)
        self.assertEqual(result["contributing_edges"][0]["documentation_completeness"], 0)
        self.assertEqual(result["contributing_edges"][0]["adjustment"], -5.0)

    def test_own_score_blended_with_inherited(self):
        headers = self._register_and_login(f"blend{self._n}@a.com", f"Blend Org {self._n}")

        source_id = self._scan_dataset(headers, f"source_{self._n}")
        downstream_id = self._scan_dataset(headers, f"downstream_{self._n}")

        self._set_quality_score(source_id, 50.0)
        self._set_quality_score(downstream_id, 70.0)

        self._create_edge(
            headers, source_id, downstream_id,
            transformation_type="SQL_TRANSFORM",
            transformation_description="Aggregates daily orders into a summary table.",
            filter_logic="WHERE order_status = 'completed'",
        )

        result = self._get_effective(headers, downstream_id)

        self.assertEqual(result["own_score"], 70.0)
        # inherited = 50 + 5 = 55, blended = (70 + 55) / 2 = 62.5
        self.assertEqual(result["effective_score"], 62.5)

    def test_multiple_upstream_edges_are_averaged(self):
        headers = self._register_and_login(f"multi{self._n}@a.com", f"Multi Org {self._n}")

        source1_id = self._scan_dataset(headers, f"source1_{self._n}")
        source2_id = self._scan_dataset(headers, f"source2_{self._n}")
        downstream_id = self._scan_dataset(headers, f"downstream_{self._n}")

        self._set_quality_score(source1_id, 50.0)
        self._set_quality_score(source2_id, 80.0)
        self._clear_quality_profile(downstream_id)

        self._create_edge(
            headers, source1_id, downstream_id,
            transformation_type="SQL_TRANSFORM",
            transformation_description="Aggregates daily orders into a summary table.",
            filter_logic="WHERE order_status = 'completed'",
        )  # contribution: 50 + 5 = 55
        self._create_edge(headers, source2_id, downstream_id)  # undocumented: 80 - 5 = 75

        result = self._get_effective(headers, downstream_id)

        self.assertEqual(result["effective_score"], 65.0)
        self.assertEqual(len(result["contributing_edges"]), 2)

    def test_no_upstream_lineage_returns_own_score_unchanged(self):
        headers = self._register_and_login(f"solo{self._n}@a.com", f"Solo Org {self._n}")

        dataset_id = self._scan_dataset(headers, f"solo_{self._n}")
        self._set_quality_score(dataset_id, 42.3)

        result = self._get_effective(headers, dataset_id)

        self.assertEqual(result["own_score"], 42.3)
        self.assertEqual(result["effective_score"], 42.3)
        self.assertEqual(result["contributing_edges"], [])

    def test_cyclic_lineage_does_not_hang(self):
        headers = self._register_and_login(f"cycle{self._n}@a.com", f"Cycle Org {self._n}")

        a_id = self._scan_dataset(headers, f"a_{self._n}")
        b_id = self._scan_dataset(headers, f"b_{self._n}")

        self._set_quality_score(a_id, 50.0)
        self._set_quality_score(b_id, 60.0)

        self._create_edge(headers, a_id, b_id, transformation_type="SQL")
        self._create_edge(headers, b_id, a_id, transformation_type="SQL")

        # Just needs to return promptly with a 200 - the cycle guard is
        # what's under test, not a specific numeric outcome.
        result = self._get_effective(headers, a_id)
        self.assertIn("effective_score", result)

    def test_effective_score_is_tenant_scoped(self):
        headers_a = self._register_and_login(f"tenA{self._n}@a.com", f"Tenant A {self._n}")
        headers_b = self._register_and_login(f"tenB{self._n}@a.com", f"Tenant B {self._n}")

        dataset_id = self._scan_dataset(headers_a, f"scoped_{self._n}")

        r = self.client.get(f"/api/data-quality/dataset/{dataset_id}/effective", headers=headers_b)
        self.assertEqual(r.status_code, 404)


if __name__ == "__main__":
    unittest.main()
