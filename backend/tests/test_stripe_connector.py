"""
Unit tests for app/connectors/stripe_scanner.py against a mocked
`requests` module - there's no live Stripe account in this
environment. Covers the happy path across all four Stripe objects,
type inference on Stripe's actual field shapes (integer amounts,
boolean flags, nested objects flattened to JSON), a rejected API key,
an unreachable API, an object type with no records, and a missing
API key rejected before any request.
"""

import json
import unittest
from unittest.mock import MagicMock, patch

import requests

from app.connectors.stripe_scanner import (
    StripeConnectionError,
    scan_stripe_source,
)


def _response(status_code=200, json_body=None, text=""):
    response = MagicMock()
    response.status_code = status_code
    response.json.return_value = json_body if json_body is not None else {}
    response.text = text
    return response


CUSTOMER_RECORD = {
    "id": "cus_123",
    "email": "a@b.com",
    "name": "Ada Lovelace",
    "balance": 0,
    "delinquent": False,
    "address": {"city": "London", "country": "GB"},
}

CHARGE_RECORD = {
    "id": "ch_123",
    "amount": 2000,
    "currency": "usd",
    "customer": "cus_123",
    "paid": True,
    "created": 1700000000,
}


def _list_response(records):
    return _response(status_code=200, json_body={"data": records, "has_more": False})


class ScanStripeSourceTests(unittest.TestCase):

    @patch("app.connectors.stripe_scanner.requests.get")
    def test_happy_path_builds_one_dataset_per_object_type(self, mock_get):
        mock_get.side_effect = [
            _list_response([CUSTOMER_RECORD, {**CUSTOMER_RECORD, "id": "cus_456", "email": None}]),
            _list_response([CHARGE_RECORD]),
            _list_response([]),
            _list_response([]),
        ]

        result = scan_stripe_source({"api_key": "sk_test_abc"})

        self.assertEqual(len(result["datasets"]), 2)
        self.assertEqual(result["foreign_keys"], [])

        by_name = {d["table_name"]: d for d in result["datasets"]}
        self.assertIn("customers", by_name)
        self.assertIn("charges", by_name)
        self.assertNotIn("invoices", by_name)
        self.assertNotIn("subscriptions", by_name)

        customers = by_name["customers"]
        self.assertEqual(customers["schema_name"], "stripe")
        self.assertEqual(customers["row_count"], 2)

        columns_by_name = {c[0]: c for c in customers["columns"]}
        self.assertEqual(columns_by_name["email"][1], "varchar")
        # One of the two sampled customers has email=None.
        self.assertEqual(columns_by_name["email"][2], "YES")
        self.assertEqual(columns_by_name["delinquent"][1], "boolean")

    @patch("app.connectors.stripe_scanner.requests.get")
    def test_amounts_and_flags_are_typed_correctly(self, mock_get):
        mock_get.side_effect = [
            _list_response([]),
            _list_response([CHARGE_RECORD, {**CHARGE_RECORD, "id": "ch_456"}]),
            _list_response([]),
            _list_response([]),
        ]

        result = scan_stripe_source({"api_key": "sk_test_abc"})
        charges = result["datasets"][0]
        columns_by_name = {c[0]: c for c in charges["columns"]}

        self.assertEqual(columns_by_name["amount"][1], "integer")
        self.assertEqual(columns_by_name["paid"][1], "boolean")
        self.assertEqual(columns_by_name["created"][1], "integer")
        self.assertEqual(columns_by_name["currency"][1], "varchar")

    @patch("app.connectors.stripe_scanner.requests.get")
    def test_nested_objects_are_flattened_to_json_strings(self, mock_get):
        mock_get.side_effect = [
            _list_response([CUSTOMER_RECORD]),
            _list_response([]),
            _list_response([]),
            _list_response([]),
        ]

        result = scan_stripe_source({"api_key": "sk_test_abc"})
        customers = result["datasets"][0]

        address_sample = customers["column_samples"]["address"][0]
        self.assertEqual(json.loads(address_sample), {"city": "London", "country": "GB"})

    @patch("app.connectors.stripe_scanner.requests.get")
    def test_object_type_with_no_records_produces_no_dataset(self, mock_get):
        mock_get.side_effect = [_list_response([])] * 4

        result = scan_stripe_source({"api_key": "sk_test_abc"})
        self.assertEqual(result["datasets"], [])

    @patch("app.connectors.stripe_scanner.requests.get")
    def test_rejected_api_key_raises_clear_error(self, mock_get):
        mock_get.return_value = _response(status_code=401, text="Invalid API Key provided")

        with self.assertRaises(StripeConnectionError) as ctx:
            scan_stripe_source({"api_key": "sk_test_bad"})

        self.assertIn("rejected", str(ctx.exception))

    @patch("app.connectors.stripe_scanner.requests.get")
    def test_unreachable_api_raises_clear_error(self, mock_get):
        mock_get.side_effect = requests.ConnectionError("name resolution failed")

        with self.assertRaises(StripeConnectionError) as ctx:
            scan_stripe_source({"api_key": "sk_test_abc"})

        self.assertIn("Unable to reach", str(ctx.exception))

    def test_missing_api_key_rejected_before_any_request(self):
        with self.assertRaises(StripeConnectionError):
            scan_stripe_source({})


if __name__ == "__main__":
    unittest.main()
