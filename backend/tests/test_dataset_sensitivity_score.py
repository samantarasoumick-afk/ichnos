"""
Regression test: Dataset.sensitivity_score used to only tally PII and
SENSITIVE column classifications, silently ignoring FINANCIAL (the
classification the privacy engine assigns to card numbers, bank
accounts, IFSC codes, etc). A dataset made entirely of financial
identifiers - e.g. a payments table - showed up as LOW sensitivity
everywhere the badge is used, which undersells real risk in exactly
the tool meant to surface it.
"""

import unittest

from app.models.dataset import Dataset
from app.models.column import DatasetColumn


def _col(classification):
    c = DatasetColumn()
    c.classification = classification
    return c


class DatasetSensitivityScoreTests(unittest.TestCase):

    def test_no_columns_is_low(self):
        d = Dataset()
        d.columns = []
        self.assertEqual(d.sensitivity_score, "LOW")

    def test_single_financial_column_is_medium(self):
        d = Dataset()
        d.columns = [_col("FINANCIAL")]
        self.assertEqual(d.sensitivity_score, "LOW")

    def test_two_financial_columns_is_medium(self):
        d = Dataset()
        d.columns = [_col("FINANCIAL"), _col("FINANCIAL")]
        self.assertEqual(d.sensitivity_score, "MEDIUM")

    def test_financial_and_sensitive_combine(self):
        d = Dataset()
        d.columns = [_col("FINANCIAL"), _col("SENSITIVE")]
        self.assertEqual(d.sensitivity_score, "MEDIUM")

    def test_two_pii_columns_is_high(self):
        d = Dataset()
        d.columns = [_col("PII"), _col("PII")]
        self.assertEqual(d.sensitivity_score, "HIGH")

    def test_unclassified_only_is_low(self):
        d = Dataset()
        d.columns = [_col("UNCLASSIFIED"), _col("UNCLASSIFIED")]
        self.assertEqual(d.sensitivity_score, "LOW")


if __name__ == "__main__":
    unittest.main()
