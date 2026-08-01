"""
Every steward-assigned or computed classification a dataset can carry
(system_role, certification, contract_status, governance_status,
data_category, freshness_status, operational_status, sensitivity_score,
trust_score) should be searchable by its plain-English label, not just
answerable via a full Ask'Fe' question - see
app/services/catalog_search_service.py's _dataset_document(). Before
this, none of these fields were part of the indexed text at all, so a
bare keyword search for e.g. "system of record" or "breached contract"
came back empty even though a dataset genuinely had that attribute
assigned.
"""

import unittest
import uuid

from fastapi.testclient import TestClient

from app.db.database import SessionLocal
from app.main import app
from app.models.dataset import Dataset
from app.models.organization import Organization
from app.models.source import DataSource
from app.models.user import User
from app.services.catalog_search_service import _dataset_document


class DatasetDocumentAttributeLabelTests(unittest.TestCase):
    """
    Direct unit tests of _dataset_document() - constructs a Dataset with
    a specific combination of assigned attributes and checks the
    resulting corpus text carries a human-readable label for each one,
    independent of the search-ranking/API layer above it.
    """

    def setUp(self):
        self._n = uuid.uuid4().hex[:8]
        self.db = SessionLocal()

    def tearDown(self):
        self.db.close()

    def _make_dataset(self, **kwargs):
        org = Organization(name=f"AttrDoc Org {self._n}", slug=uuid.uuid4().hex[:8])
        self.db.add(org)
        self.db.flush()

        source = DataSource(name="src", type="postgresql", connection_config={}, organization_id=org.id)
        self.db.add(source)
        self.db.flush()

        dataset = Dataset(
            name="widgets", schema_name="public",
            source_id=source.id, organization_id=org.id,
            **kwargs,
        )
        self.db.add(dataset)
        self.db.commit()
        self.db.refresh(dataset)
        return dataset

    def test_system_of_record_is_indexed(self):
        dataset = self._make_dataset(system_role="SYSTEM_OF_RECORD")
        doc = _dataset_document(dataset)
        self.assertIn("System of Record", doc.text)

    def test_system_of_reference_is_indexed(self):
        dataset = self._make_dataset(system_role="SYSTEM_OF_REFERENCE")
        doc = _dataset_document(dataset)
        self.assertIn("System of Reference", doc.text)

    def test_certification_is_indexed(self):
        dataset = self._make_dataset(certification="VERIFIED")
        doc = _dataset_document(dataset)
        self.assertIn("verified", doc.text)

    def test_data_category_is_indexed(self):
        dataset = self._make_dataset(data_category="MASTER")
        doc = _dataset_document(dataset)
        self.assertIn("master data", doc.text)

    def test_no_contract_is_indexed(self):
        dataset = self._make_dataset()
        doc = _dataset_document(dataset)
        self.assertIn("no data contract", doc.text)

    def test_sensitivity_and_governance_and_freshness_and_operational_and_trust_are_indexed(self):
        # A dataset with no columns and never scanned is a fixed,
        # predictable combination of every remaining computed property
        # (see app/models/dataset.py): sensitivity_score=LOW (no
        # columns), governance_status=HEALTHY (not HIGH/MEDIUM
        # sensitivity), freshness_status=STALE (never scanned),
        # operational_status=UNSTABLE (quality_score=0 with no
        # columns), trust_score=80 (100 - 20 for STALE freshness).
        # last_scanned_at is set to None directly on the already-
        # persisted object rather than passed to the constructor - the
        # Column's Python-side default (default=datetime.utcnow) is
        # applied by SQLAlchemy at flush time whenever the attribute
        # isn't holding a real value, which happens even for an
        # explicit None passed to __init__.
        dataset = self._make_dataset()
        dataset.last_scanned_at = None
        doc = _dataset_document(dataset)
        self.assertIn("low sensitivity", doc.text)
        self.assertIn("healthy governance status", doc.text)
        self.assertIn("stale", doc.text)
        self.assertIn("unstable operational status", doc.text)
        # 100 - 20 (STALE freshness) = 80, which falls in the "high"
        # trust bucket (>=80) even with one penalty applied.
        self.assertIn("high trust score", doc.text)


class DatasetAttributeSearchApiTests(unittest.TestCase):
    """End-to-end: GET /api/search should surface a dataset by an assigned
    attribute label, not just its name/description/owner."""

    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)

    def setUp(self):
        self._n = uuid.uuid4().hex[:8]
        self.db = SessionLocal()

    def tearDown(self):
        self.db.close()

    def _register_and_login(self, email, org_name):
        r = self.client.post("/api/auth/register", json={
            "email": email, "password": "password123", "organization_name": org_name,
        })
        self.assertEqual(r.status_code, 200, r.text)
        r = self.client.post("/api/auth/login", json={"email": email, "password": "password123"})
        return {"Authorization": f"Bearer {r.json()['access_token']}"}

    def test_system_of_record_dataset_is_searchable_by_label(self):
        email = f"attrsearch{self._n}@a.com"
        headers = self._register_and_login(email, f"Attr Search Org {self._n}")

        user = self.db.query(User).filter(User.email == email).first()
        self.assertIsNotNone(user)

        source = DataSource(name="Warehouse", type="postgresql", connection_config={}, organization_id=user.organization_id)
        self.db.add(source)
        self.db.flush()

        dataset_name = f"authoritative_customers_{self._n}"
        dataset = Dataset(
            name=dataset_name, schema_name="public",
            source_id=source.id, organization_id=user.organization_id,
            system_role="SYSTEM_OF_RECORD",
        )
        self.db.add(dataset)
        self.db.commit()

        r = self.client.get("/api/search?q=system+of+record", headers=headers)
        self.assertEqual(r.status_code, 200, r.text)

        dataset_hits = [item for item in r.json()["results"] if item["type"] == "dataset"]
        self.assertEqual(len(dataset_hits), 1, r.json()["results"])
        self.assertEqual(dataset_hits[0]["label"], f"public.{dataset_name}")


if __name__ == "__main__":
    unittest.main()
