"""
Unit tests for app/connectors/s3_scanner.py against a mocked boto3 S3
client - there's no live S3 bucket in this environment. Covers the
grouping logic (nested files -> one dataset, flat files -> a single
prefix-named dataset), CSV vs newline-delimited JSON sniffing, the
truncated-large-file row_count fallback, and that unsupported file
extensions never even reach the grouping step.
"""

import io
import unittest
from unittest.mock import MagicMock, patch

from botocore.exceptions import ClientError

from app.connectors.s3_scanner import scan_s3_source, SAMPLE_BYTES


def _body(content: bytes):
    stream = MagicMock()
    stream.read.return_value = content
    return {"Body": stream}


def _make_client(objects, get_object_by_key, list_error=None):
    client = MagicMock()

    paginator = MagicMock()

    if list_error:
        def paginate(**kwargs):
            raise list_error
        paginator.paginate.side_effect = paginate
    else:
        paginator.paginate.return_value = [{"Contents": objects}]

    client.get_paginator.return_value = paginator

    def get_object(Bucket, Key, **kwargs):
        return get_object_by_key[Key]

    client.get_object.side_effect = get_object

    return client


class ScanS3SourceTests(unittest.TestCase):

    @patch("app.connectors.s3_scanner.boto3.client")
    def test_nested_files_group_into_one_dataset(self, mock_boto_client):
        csv_content = b"id,email\n1,a@b.com\n2,c@d.com\n"

        objects = [
            {"Key": "orders/part-0001.csv", "Size": len(csv_content)},
            {"Key": "orders/part-0002.csv", "Size": len(csv_content)},
        ]

        mock_boto_client.return_value = _make_client(
            objects,
            {"orders/part-0001.csv": _body(csv_content)},
        )

        result = scan_s3_source({"bucket": "my-bucket"})

        self.assertEqual(len(result["datasets"]), 1)
        dataset = result["datasets"][0]
        self.assertEqual(dataset["schema_name"], "my-bucket")
        self.assertEqual(dataset["table_name"], "orders")
        self.assertEqual(dataset["row_count"], 2)
        self.assertEqual(
            [c[0] for c in dataset["columns"]],
            ["id", "email"],
        )
        self.assertEqual(dataset["columns"][0][1], "integer")
        self.assertEqual(result["foreign_keys"], [])

    @patch("app.connectors.s3_scanner.boto3.client")
    def test_flat_files_group_under_prefix_name(self, mock_boto_client):
        csv_content = b"id\n1\n2\n"

        objects = [
            {"Key": "exports/customers.csv", "Size": len(csv_content)},
        ]

        mock_boto_client.return_value = _make_client(
            objects,
            {"exports/customers.csv": _body(csv_content)},
        )

        result = scan_s3_source({"bucket": "my-bucket", "prefix": "exports/"})

        self.assertEqual(len(result["datasets"]), 1)
        self.assertEqual(result["datasets"][0]["table_name"], "exports")

    @patch("app.connectors.s3_scanner.boto3.client")
    def test_ndjson_columns_inferred_from_first_record(self, mock_boto_client):
        content = (
            b'{"id": 1, "active": true}\n'
            b'{"id": 2, "active": false}\n'
        )

        objects = [{"Key": "events/log.jsonl", "Size": len(content)}]

        mock_boto_client.return_value = _make_client(
            objects,
            {"events/log.jsonl": _body(content)},
        )

        result = scan_s3_source({"bucket": "my-bucket"})

        dataset = result["datasets"][0]
        names = [c[0] for c in dataset["columns"]]
        self.assertIn("id", names)
        self.assertIn("active", names)
        self.assertEqual(dataset["row_count"], 2)

    @patch("app.connectors.s3_scanner.boto3.client")
    def test_large_file_is_sampled_not_fully_counted(self, mock_boto_client):
        # Bigger than SAMPLE_BYTES so the scanner issues a ranged GET
        # and can't claim an exact row count.
        big_size = SAMPLE_BYTES + 1
        sample_content = b"id,email\n1,a@b.com\n2,c@d.com\n3,truncat"

        objects = [{"Key": "big/data.csv", "Size": big_size}]

        mock_boto_client.return_value = _make_client(
            objects,
            {"big/data.csv": _body(sample_content)},
        )

        result = scan_s3_source({"bucket": "my-bucket"})

        dataset = result["datasets"][0]
        # The last (possibly-partial) row is dropped, and row_count
        # reports 0 (unknown/lower-bound) rather than a false exact
        # count, since only a prefix of the object was read.
        self.assertEqual(dataset["row_count"], 0)
        self.assertIn("a@b.com", dataset["column_samples"]["email"])
        self.assertNotIn("truncat", str(dataset["column_samples"]))

    @patch("app.connectors.s3_scanner.boto3.client")
    def test_unsupported_extensions_are_ignored(self, mock_boto_client):
        objects = [
            {"Key": "data/report.parquet", "Size": 100},
            {"Key": "data/notes.txt", "Size": 100},
        ]

        mock_boto_client.return_value = _make_client(objects, {})

        result = scan_s3_source({"bucket": "my-bucket"})

        self.assertEqual(result["datasets"], [])

    @patch("app.connectors.s3_scanner.boto3.client")
    def test_list_failure_propagates(self, mock_boto_client):
        error = ClientError(
            error_response={"Error": {"Code": "NoSuchBucket", "Message": "no such bucket"}},
            operation_name="ListObjectsV2",
        )

        mock_boto_client.return_value = _make_client([], {}, list_error=error)

        with self.assertRaises(ClientError):
            scan_s3_source({"bucket": "does-not-exist"})


if __name__ == "__main__":
    unittest.main()
