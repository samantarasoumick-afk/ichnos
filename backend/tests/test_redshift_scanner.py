"""
Unit tests for app/connectors/redshift_scanner.py against a mocked
psycopg2 connection/cursor - there's no live Redshift cluster in this
environment. redshift_scanner reuses psycopg2 (Redshift is wire- and
catalog-compatible with Postgres) and composes queries with
psycopg2.sql, so - unlike the raw-string MySQL scanner - the mock
here drives fetchall()/fetchone() by call order rather than by
inspecting the executed query text.
"""

import unittest
from unittest.mock import MagicMock, patch

import psycopg2

from app.connectors.redshift_scanner import scan_redshift_source, DEFAULT_PORT


class ScanRedshiftSourceTests(unittest.TestCase):

    @patch("app.connectors.redshift_scanner.psycopg2.connect")
    def test_scan_returns_expected_shape_for_single_table(self, mock_connect):
        columns = [("id", "integer", "NO"), ("email", "character varying", "YES")]
        stats_row = {"nn_id": 2, "dc_id": 2, "nn_email": 2, "dc_email": 2}
        samples = [(1, "a@b.com"), (2, "c@d.com")]

        cursor = MagicMock()
        # Call order: tables, foreign_keys, columns(for table), sample_rows
        cursor.fetchall.side_effect = [
            [("public", "widgets")],
            [],
            columns,
            samples,
        ]
        # Call order: COUNT(*), stats
        cursor.fetchone.side_effect = [
            (2,),
            tuple(stats_row.values()),
        ]
        cursor.description = [(k,) for k in stats_row.keys()]

        connection = MagicMock()
        connection.cursor.return_value = cursor
        mock_connect.return_value = connection

        result = scan_redshift_source({
            "host": "my-cluster.abc123.us-east-1.redshift.amazonaws.com",
            "database": "dev",
            "user": "admin",
            "password": "secret",
        })

        self.assertEqual(len(result["datasets"]), 1)
        dataset = result["datasets"][0]
        self.assertEqual(dataset["schema_name"], "public")
        self.assertEqual(dataset["table_name"], "widgets")
        self.assertEqual(dataset["row_count"], 2)
        self.assertEqual(dataset["column_stats"]["email"], {"non_null": 2, "distinct": 2})
        self.assertIn("a@b.com", dataset["column_samples"]["email"])
        self.assertEqual(result["foreign_keys"], [])

        # Defaults to Redshift's 5439, not Postgres's 5432, when the
        # caller doesn't specify a port.
        _, connect_kwargs = mock_connect.call_args
        self.assertEqual(connect_kwargs["port"], DEFAULT_PORT)

    @patch("app.connectors.redshift_scanner.psycopg2.connect")
    def test_explicit_port_is_respected(self, mock_connect):
        cursor = MagicMock()
        cursor.fetchall.side_effect = [[], []]
        connection = MagicMock()
        connection.cursor.return_value = cursor
        mock_connect.return_value = connection

        scan_redshift_source({
            "host": "x",
            "port": 5555,
            "database": "dev",
            "user": "admin",
            "password": "secret",
        })

        _, connect_kwargs = mock_connect.call_args
        self.assertEqual(connect_kwargs["port"], 5555)

    @patch("app.connectors.redshift_scanner.psycopg2.connect")
    def test_connection_failure_raises_clear_error(self, mock_connect):
        mock_connect.side_effect = psycopg2.OperationalError("connection refused")

        with self.assertRaises(psycopg2.OperationalError) as context:
            scan_redshift_source({
                "host": "unreachable",
                "database": "dev",
                "user": "admin",
                "password": "secret",
            })

        self.assertIn("Unable to connect to Redshift", str(context.exception))

    @patch("app.connectors.redshift_scanner.psycopg2.connect")
    def test_foreign_key_query_failure_does_not_crash_scan(self, mock_connect):
        """
        Redshift foreign keys are informational-only and frequently
        unavailable to the connecting role/cluster config - a failure
        fetching them shouldn't take down the rest of the scan.
        """

        cursor = MagicMock()
        # Call order: tables, foreign_keys (raises), columns(for table)
        cursor.fetchall.side_effect = [
            [("public", "widgets")],
            Exception("permission denied for constraint views"),
            [],
        ]
        # Call order: COUNT(*) -> 0 rows, so stats/sample queries are
        # never reached (row_count > 0 guards both).
        cursor.fetchone.side_effect = [(0,)]

        connection = MagicMock()
        connection.cursor.return_value = cursor
        mock_connect.return_value = connection

        result = scan_redshift_source({
            "host": "x",
            "database": "dev",
            "user": "admin",
            "password": "secret",
        })

        self.assertEqual(result["foreign_keys"], [])
        # Scan still proceeds to enumerate the (empty-columned) table.
        self.assertEqual(len(result["datasets"]), 1)


if __name__ == "__main__":
    unittest.main()
