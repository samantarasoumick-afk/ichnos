"""
Integration test for the scan diff/upsert logic (the fix for the
"rescan deletes and recreates all columns, destroying steward
corrections" bug).

Drives two full scans through the real FastAPI app + HTTP layer, with
only the scanner dispatch (app.api.scanner.get_scanner) mocked out to
return a fake scan function - no real Postgres needed. Everything
else, including auth, tenant scoping, the privacy engine, and data
quality profiling, runs for real.
"""

import unittest
import uuid
from unittest.mock import patch, MagicMock

from fastapi.testclient import TestClient

from app.db.database import SessionLocal
from app.main import app
from app.models.column import DatasetColumn


FIRST_SCAN = {
    "datasets": [{
        "schema_name": "public",
        "table_name": "customers",
        "columns": [
            ("id", "integer", "NO"),
            ("email", "text", "YES"),
            ("phone", "text", "YES"),
            ("legacy_code", "text", "YES"),
        ],
        "row_count": 3,
        "column_stats": {
            "id": {"non_null": 3, "distinct": 3},
            "email": {"non_null": 3, "distinct": 3},
            "phone": {"non_null": 3, "distinct": 3},
            "legacy_code": {"non_null": 2, "distinct": 2},
        },
        "column_samples": {
            "id": ["1", "2", "3"],
            "email": ["a@b.com", "c@d.com", "e@f.com"],
            "phone": ["9876543210", "9123456780", "9988776655"],
            "legacy_code": ["x", "y"],
        },
    }],
    "foreign_keys": [],
}

# Second scan: "legacy_code" dropped from the source table, a new
# "signup_date" column appears, "phone" and "email" and "id" remain.
SECOND_SCAN = {
    "datasets": [{
        "schema_name": "public",
        "table_name": "customers",
        "columns": [
            ("id", "integer", "NO"),
            ("email", "text", "YES"),
            ("phone", "text", "YES"),
            ("signup_date", "date", "YES"),
        ],
        "row_count": 4,
        "column_stats": {
            "id": {"non_null": 4, "distinct": 4},
            "email": {"non_null": 4, "distinct": 4},
            "phone": {"non_null": 4, "distinct": 4},
            "signup_date": {"non_null": 4, "distinct": 4},
        },
        "column_samples": {
            "id": ["1", "2", "3", "4"],
            "email": ["a@b.com", "c@d.com", "e@f.com", "g@h.com"],
            # Deliberately different sample values than the first scan -
            # if "phone" is still auto-classified, this would still
            # classify the same way, so this alone doesn't prove
            # preservation. The test asserts on classification_source
            # and the steward's custom label directly, which does.
            "phone": ["9000000000", "9111111111", "9222222222", "9333333333"],
            "signup_date": ["2024-01-01", "2024-02-02", "2024-03-03", "2024-04-04"],
        },
    }],
    "foreign_keys": [],
}


class ScanColumnDiffingTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)

    def setUp(self):
        unique = uuid.uuid4().hex[:8]
        self.email = f"steward-{unique}@rescan-test.com"

        r = self.client.post("/api/auth/register", json={
            "email": self.email,
            "password": "password123",
            "organization_name": f"Rescan Test Org {unique}",
        })
        self.assertEqual(r.status_code, 200, r.text)

        r = self.client.post("/api/auth/login", json={
            "email": self.email,
            "password": "password123",
        })
        self.token = r.json()["access_token"]
        self.headers = {"Authorization": f"Bearer {self.token}"}

        r = self.client.post("/api/sources", headers=self.headers, json={
            "name": f"Rescan Test Source {unique}",
            "type": "postgresql",
            "connection_config": {"host": "x", "database": "y", "user": "z", "password": "p", "port": 5432},
        })
        self.assertEqual(r.status_code, 200, r.text)
        self.source_id = r.json()["id"]

    def _columns_by_name(self, dataset_id):
        db = SessionLocal()
        try:
            rows = db.query(DatasetColumn).filter(DatasetColumn.dataset_id == dataset_id).all()
            return {c.name: c for c in rows}
        finally:
            db.close()

    @patch("app.api.scanner.get_scanner")
    def test_rescan_preserves_manual_override_and_tracks_drift(self, mock_get_scanner):
        mock_scan = MagicMock(return_value=FIRST_SCAN)
        mock_get_scanner.return_value = mock_scan

        r = self.client.post(f"/api/scanner/{self.source_id}", headers=self.headers)
        self.assertEqual(r.status_code, 200, r.text)

        r = self.client.get("/api/datasets/", headers=self.headers)
        datasets = r.json()
        self.assertEqual(len(datasets), 1)
        dataset_id = datasets[0]["id"]

        columns = self._columns_by_name(dataset_id)
        self.assertEqual(set(columns.keys()), {"id", "email", "phone", "legacy_code"})
        self.assertEqual(columns["phone"].classification_source, "AUTO")
        self.assertEqual(columns["phone"].classification, "PII")

        # Simulate a steward manually overriding the "phone" column's
        # classification (no PATCH-column endpoint exists yet, so this
        # models it directly against the DB, same as a future steward
        # edit endpoint would).
        db = SessionLocal()
        try:
            phone = db.query(DatasetColumn).filter(
                DatasetColumn.dataset_id == dataset_id,
                DatasetColumn.name == "phone",
            ).first()
            phone.classification = "INTERNAL_USE_ONLY"
            phone.classification_source = "MANUAL"
            phone.consent_required = False
            db.commit()
        finally:
            db.close()

        # Second scan: legacy_code dropped, signup_date added, phone's
        # underlying sampled values change completely.
        mock_scan.return_value = SECOND_SCAN

        r = self.client.post(f"/api/scanner/{self.source_id}", headers=self.headers)
        self.assertEqual(r.status_code, 200, r.text)

        columns = self._columns_by_name(dataset_id)

        # legacy_code was dropped from the source -> removed, not
        # left behind as a ghost row.
        self.assertNotIn("legacy_code", columns)

        # signup_date is brand new -> added and auto-classified.
        self.assertIn("signup_date", columns)
        self.assertEqual(columns["signup_date"].classification_source, "AUTO")

        # phone: the steward's manual override survives the rescan
        # untouched, even though the underlying data changed.
        self.assertEqual(columns["phone"].classification_source, "MANUAL")
        self.assertEqual(columns["phone"].classification, "INTERNAL_USE_ONLY")
        self.assertFalse(columns["phone"].consent_required)

        # email stayed AUTO and got re-classified normally.
        self.assertEqual(columns["email"].classification_source, "AUTO")
        self.assertEqual(columns["email"].classification, "PII")

        # id's objective schema facts still refresh even though it's
        # untouched data-wise.
        self.assertEqual(columns["id"].data_type, "integer")

    @patch("app.api.scanner.get_scanner")
    def test_data_quality_profile_created_from_real_scan_stats(self, mock_get_scanner):
        mock_scan = MagicMock(return_value=FIRST_SCAN)
        mock_get_scanner.return_value = mock_scan

        r = self.client.post(f"/api/scanner/{self.source_id}", headers=self.headers)
        self.assertEqual(r.status_code, 200, r.text)

        r = self.client.get("/api/datasets/", headers=self.headers)
        dataset_id = r.json()[0]["id"]

        r = self.client.get(f"/api/data-quality/dataset/{dataset_id}", headers=self.headers)
        self.assertEqual(r.status_code, 200, r.text)

        quality = r.json()
        # legacy_code is 2/3 non-null -> drags completeness below 100
        self.assertLess(quality["completeness"], 100.0)
        self.assertGreater(quality["completeness"], 0.0)


if __name__ == "__main__":
    unittest.main()
