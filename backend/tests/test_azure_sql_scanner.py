"""
Unit tests for app/connectors/azure_sql_scanner.py against a mocked
pymssql connection/cursor - there's no live Azure SQL/Synapse instance
in this environment. Same query-shaping/result-assembly approach as
test_mysql_scanner.py: drive fetchone()/fetchall() by inspecting which
query was just executed.
"""

import unittest
from unittest.mock import MagicMock, patch

import pymssql

from app.connectors.azure_sql_scanner import (
    _quote_ident,
    scan_azure_sql_source,
    DEFAULT_PORT,
)


class QuoteIdentTests(unittest.TestCase):

    def test_wraps_in_brackets(self):
        self.assertEqual(_quote_ident("users"), "[users]")

    def test_escapes_embedded_closing_bracket(self):
        self.assertEqual(_quote_ident("weird]name"), "[weird]]name]")


class ScanAzureSqlSourceTests(unittest.TestCase):

    def _make_cursor(self, table_rows, columns_by_table, foreign_keys, row_counts, stats_row, sample_rows):

        cursor = MagicMock()
        call_log = {}

        def execute(query, params=None):
            call_log["last_query"] = query.strip()

        def fetchall():
            q = call_log["last_query"]
            if "FROM INFORMATION_SCHEMA.TABLES" in q:
                return table_rows
            if "FROM INFORMATION_SCHEMA.TABLE_CONSTRAINTS" in q:
                return foreign_keys
            if "FROM INFORMATION_SCHEMA.COLUMNS" in q:
                return columns_by_table
            if q.startswith("SELECT TOP"):
                return sample_rows
            return []

        def fetchone():
            q = call_log["last_query"]
            if q.startswith("SELECT COUNT(*)"):
                return (row_counts,)
            if "nn_" in q or "dc_" in q:
                return tuple(stats_row.values())
            return None

        cursor.execute.side_effect = execute
        cursor.fetchall.side_effect = fetchall
        cursor.fetchone.side_effect = fetchone
        cursor.description = [(k,) for k in stats_row.keys()]

        return cursor

    @patch("app.connectors.azure_sql_scanner.pymssql.connect")
    def test_scan_returns_expected_shape_for_single_table(self, mock_connect):
        columns = [("id", "int", "NO"), ("email", "varchar", "YES")]
        stats_row = {"nn_id": 2, "dc_id": 2, "nn_email": 2, "dc_email": 2}
        samples = [(1, "a@b.com"), (2, "c@d.com")]

        cursor = self._make_cursor(
            table_rows=[("dbo", "widgets")],
            columns_by_table=columns,
            foreign_keys=[],
            row_counts=2,
            stats_row=stats_row,
            sample_rows=samples,
        )

        connection = MagicMock()
        connection.cursor.return_value = cursor
        mock_connect.return_value = connection

        result = scan_azure_sql_source({
            "host": "myserver.database.windows.net",
            "database": "app_db",
            "user": "admin",
            "password": "secret",
        })

        self.assertEqual(len(result["datasets"]), 1)
        dataset = result["datasets"][0]
        self.assertEqual(dataset["schema_name"], "dbo")
        self.assertEqual(dataset["table_name"], "widgets")
        self.assertEqual(dataset["row_count"], 2)
        self.assertEqual(dataset["column_stats"]["email"], {"non_null": 2, "distinct": 2})
        self.assertIn("a@b.com", dataset["column_samples"]["email"])
        self.assertEqual(result["foreign_keys"], [])

        _, connect_kwargs = mock_connect.call_args
        self.assertEqual(connect_kwargs["port"], str(DEFAULT_PORT))

    @patch("app.connectors.azure_sql_scanner.pymssql.connect")
    def test_connection_failure_raises_clear_error(self, mock_connect):
        mock_connect.side_effect = pymssql.OperationalError("connection refused")

        with self.assertRaises(pymssql.OperationalError) as context:
            scan_azure_sql_source({
                "host": "unreachable",
                "database": "app_db",
                "user": "admin",
                "password": "secret",
            })

        self.assertIn("Unable to connect to Azure SQL", str(context.exception))

    @patch("app.connectors.azure_sql_scanner.pymssql.connect")
    def test_foreign_key_query_failure_does_not_crash_scan(self, mock_connect):
        """
        Synapse dedicated SQL pools in particular often can't see the
        full constraint-view chain - that shouldn't take down the
        rest of the scan.
        """

        cursor = MagicMock()
        call_log = {}

        def execute(query, params=None):
            call_log["last_query"] = query.strip()
            if "FROM INFORMATION_SCHEMA.TABLE_CONSTRAINTS" in query:
                raise Exception("feature not supported")

        def fetchall():
            q = call_log["last_query"]
            if "FROM INFORMATION_SCHEMA.TABLES" in q:
                return [("dbo", "widgets")]
            if "FROM INFORMATION_SCHEMA.COLUMNS" in q:
                return []
            return []

        def fetchone():
            return (0,)

        cursor.execute.side_effect = execute
        cursor.fetchall.side_effect = fetchall
        cursor.fetchone.side_effect = fetchone
        cursor.description = []

        connection = MagicMock()
        connection.cursor.return_value = cursor
        mock_connect.return_value = connection

        result = scan_azure_sql_source({
            "host": "x",
            "database": "app_db",
            "user": "admin",
            "password": "secret",
        })

        self.assertEqual(result["foreign_keys"], [])
        self.assertEqual(len(result["datasets"]), 1)


if __name__ == "__main__":
    unittest.main()
