import unittest
from datetime import datetime, timedelta

from app.models.dataset import Dataset
from app.models.column import DatasetColumn


def _col(consent_required=False, dpdp_category=None, confidence=0.9):
    c = DatasetColumn()
    c.consent_required = consent_required
    c.dpdp_category = dpdp_category
    c.confidence = confidence
    return c


class PrivacyScoreTests(unittest.TestCase):

    def test_no_personal_data_is_full_score(self):
        d = Dataset()
        d.columns = [_col(consent_required=False)]
        d.consent_status = "NOT_ASSESSED"
        d.retention_period_days = None
        d.created_at = datetime.utcnow()
        self.assertEqual(d.privacy_score, 100)

    def test_unassessed_consent_penalized(self):
        d = Dataset()
        d.columns = [_col(consent_required=True, dpdp_category="contact")]
        d.consent_status = "NOT_ASSESSED"
        d.purpose = "Customer support"
        d.retention_period_days = 365
        d.created_at = datetime.utcnow()
        self.assertEqual(d.privacy_score, 70)  # -30 for unassessed consent

    def test_consent_obtained_and_purpose_set_scores_higher(self):
        d = Dataset()
        d.columns = [_col(consent_required=True, dpdp_category="contact")]
        d.consent_status = "CONSENT_OBTAINED"
        d.purpose = "Customer support"
        d.retention_period_days = 365
        d.created_at = datetime.utcnow()
        self.assertEqual(d.privacy_score, 100)

    def test_missing_purpose_penalized(self):
        d = Dataset()
        d.columns = [_col(consent_required=True, dpdp_category="contact")]
        d.consent_status = "CONSENT_OBTAINED"
        d.purpose = None
        d.retention_period_days = 365
        d.created_at = datetime.utcnow()
        self.assertEqual(d.privacy_score, 85)  # -15 for missing purpose

    def test_overdue_retention_penalized(self):
        d = Dataset()
        d.columns = [_col(consent_required=True, dpdp_category="contact")]
        d.consent_status = "CONSENT_OBTAINED"
        d.purpose = "Customer support"
        d.retention_period_days = 30
        d.created_at = datetime.utcnow() - timedelta(days=60)
        self.assertEqual(d.privacy_score, 75)  # -25 for overdue retention

    def test_low_confidence_high_risk_column_penalized(self):
        d = Dataset()
        d.columns = [_col(consent_required=True, dpdp_category="health", confidence=0.5)]
        d.consent_status = "CONSENT_OBTAINED"
        d.purpose = "Care management"
        d.retention_period_days = 365
        d.created_at = datetime.utcnow()
        self.assertEqual(d.privacy_score, 90)  # -10 for low-confidence high-risk

    def test_score_never_negative(self):
        d = Dataset()
        d.columns = [_col(consent_required=True, dpdp_category="biometric", confidence=0.4)]
        d.consent_status = "NOT_ASSESSED"
        d.purpose = None
        d.retention_period_days = 30
        d.created_at = datetime.utcnow() - timedelta(days=1000)
        self.assertGreaterEqual(d.privacy_score, 0)


class RetentionStatusTests(unittest.TestCase):

    def test_not_set_without_retention_period(self):
        d = Dataset()
        d.retention_period_days = None
        d.created_at = datetime.utcnow()
        self.assertEqual(d.retention_status, "NOT_SET")

    def test_within_policy(self):
        d = Dataset()
        d.retention_period_days = 90
        d.created_at = datetime.utcnow() - timedelta(days=10)
        self.assertEqual(d.retention_status, "WITHIN_POLICY")

    def test_overdue(self):
        d = Dataset()
        d.retention_period_days = 90
        d.created_at = datetime.utcnow() - timedelta(days=100)
        self.assertEqual(d.retention_status, "OVERDUE")

    def test_falls_back_to_last_scanned_at_if_no_created_at(self):
        d = Dataset()
        d.retention_period_days = 10
        d.created_at = None
        d.last_scanned_at = datetime.utcnow() - timedelta(days=20)
        self.assertEqual(d.retention_status, "OVERDUE")


if __name__ == "__main__":
    unittest.main()
