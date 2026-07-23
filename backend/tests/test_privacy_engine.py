import unittest

from app.utils.privacy_engine import analyze_column


class PrivacyEngineTests(unittest.TestCase):

    def test_name_based_email_detection(self):
        result = analyze_column("email")
        self.assertEqual(result["classification"], "PII")
        self.assertEqual(result["dpdp_category"], "contact")
        self.assertTrue(result["consent_required"])

    def test_value_confirmation_raises_confidence(self):
        without_values = analyze_column("email")
        with_values = analyze_column("email", ["a@b.com", "c@d.org", "e@f.net"])
        self.assertGreater(with_values["confidence"], without_values["confidence"])

    def test_value_contradiction_lowers_confidence(self):
        baseline = analyze_column("email")
        contradicted = analyze_column("email", ["not-an-email", "still-not"])
        self.assertLess(contradicted["confidence"], baseline["confidence"])
        self.assertLess(contradicted["sensitivity_score"], baseline["sensitivity_score"])

    def test_uninformative_name_falls_back_to_value_sampling(self):
        result = analyze_column("field_12", ["a@b.com", "c@d.org", "e@f.net", "g@h.io"])
        self.assertEqual(result["classification"], "PII")
        self.assertEqual(result["dpdp_category"], "contact")

    def test_no_signal_is_unclassified_not_guessed(self):
        result = analyze_column("field_12", ["hello", "world"])
        self.assertEqual(result["classification"], "UNCLASSIFIED")
        self.assertFalse(result["consent_required"])

    def test_aadhaar_is_high_sensitivity_government_id(self):
        result = analyze_column("aadhaar_number")
        self.assertEqual(result["dpdp_category"], "government_id")
        self.assertEqual(result["risk_level"], "HIGH")

    def test_health_data_is_sensitive_and_requires_consent(self):
        result = analyze_column("diagnosis_notes")
        self.assertEqual(result["dpdp_category"], "health")
        self.assertTrue(result["consent_required"])

    def test_gender_is_low_risk_no_consent_required(self):
        result = analyze_column("gender")
        self.assertEqual(result["dpdp_category"], "identity")
        self.assertFalse(result["consent_required"])

    def test_sensitivity_score_is_numeric_not_a_label(self):
        result = analyze_column("email")
        self.assertIsInstance(result["sensitivity_score"], float)
        self.assertGreaterEqual(result["sensitivity_score"], 0.0)
        self.assertLessEqual(result["sensitivity_score"], 1.0)


if __name__ == "__main__":
    unittest.main()
