"""
Unit tests for the dataset auto-classification heuristic
(app/utils/data_classification.py). Pure function, no DB needed -
these lock in the keyword/shape logic so future tweaks to the
keyword lists don't silently flip the answer for the datasets the
demo narrative (and real customers) depend on.
"""

import unittest

from app.utils.data_classification import classify_data_category


class ClassifyDataCategoryTests(unittest.TestCase):

    def test_master_entity_by_name(self):
        self.assertEqual(
            classify_data_category("public", "customers", ["id", "email", "name"]),
            "MASTER",
        )
        self.assertEqual(
            classify_data_category("public", "products", ["id", "sku", "price"]),
            "MASTER",
        )

    def test_reference_lookup_by_name_and_narrow_shape(self):
        self.assertEqual(
            classify_data_category("public", "country_codes", ["code", "name"]),
            "REFERENCE",
        )
        self.assertEqual(
            classify_data_category("public", "order_status_lookup", ["status_code", "label"]),
            "REFERENCE",
        )

    def test_transactional_by_name(self):
        self.assertEqual(
            classify_data_category("public", "orders", ["order_id", "customer_id", "total_amount"]),
            "TRANSACTIONAL",
        )
        self.assertEqual(
            classify_data_category("support", "tickets", ["ticket_id", "subject", "status"]),
            "TRANSACTIONAL",
        )

    def test_analytical_by_name(self):
        self.assertEqual(
            classify_data_category("analytics_marts", "fct_customer_orders", ["customer_id", "order_total"]),
            "ANALYTICAL",
        )
        self.assertEqual(
            classify_data_category("Executive Reporting", "Revenue Dashboard", []),
            "ANALYTICAL",
        )

    def test_analytical_column_hints_break_ties(self):
        # A generically-named table with clearly derived/aggregated
        # columns should lean ANALYTICAL even without a matching name.
        self.assertEqual(
            classify_data_category(
                "public", "widgets",
                ["widget_id", "total_sales", "avg_rating", "conversion_rate"],
            ),
            "ANALYTICAL",
        )

    def test_falls_back_to_transactional_when_nothing_matches(self):
        self.assertEqual(
            classify_data_category("public", "zzz_unknown_table", ["field_a", "field_b"]),
            "TRANSACTIONAL",
        )
