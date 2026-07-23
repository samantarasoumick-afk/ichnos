"""
Unit tests for app/connectors/mysql_scanner.py against a mocked
pymysql connection/cursor - there's no live MySQL server in this
environment, so these test the query-shaping and result-assembly
logic (identifier quoting, the schema/columns/foreign-keys queries,
row/column stat collection) in isolation, the same way
postgres_scanner would need a real Postgres to integration-test.
"""

import unittest
from unittest.mock import MagicMock, patch

from app.connectors.mysql_scanner import _quote_ident, scan_mysql_source


class QuoteIdentTests(unittest.TestCase):

    def test_wraps_in_backticks(self):
        self.assertEqual(_quote_ident("users"), "`users`")

    def test_escapes_embedded_backtick(self):
        self.assertEqual(_quote_ident("weird`name"), "`weird``name`")


class ScanMysqlSourceTests(unittest.TestCase):

    def _make_cursor(self, table_names, columns_by_table, foreign_keys, row_counts, stats_row, sample_rows):
        """
        Builds a MagicMock cursor whose fetchone()/fetchall() results
        are driven by which query was just executed, matching the
        sequence scan_mysql_source actually issues: tables list, FK
        list, then per-table (columns, row count, stats, samples).

        stats_row is a plain dict; fetchone() for the stats query must
        return just the values (as the real DB-API cursor would), with
        cursor.description supplying the column names separately - the
        real code zips the two back together.
        """

        cursor = MagicMock()
        call_log = {}

        def execute(query, params=None):
            call_log["last_query"] = query.strip()

        def fetchall():
            q = call_log["last_query"]
            if "FROM information_schema.tables" in q:
                return [(name,) for name in table_names]
            if "FROM information_schema.key_column_usage" in q:
                return foreign_keys
            if "FROM information_schema.columns" in q:
                return columns_by_table
            if q.startswith("SELECT `"):
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

    @patch("app.connectors.mysql_scanner.pymysql.connect")
    def test_scan_returns_expected_shape_for_single_table(self, mock_connect):
        columns = [("id", "int", "NO"), ("email", "varchar", "YES")]
        stats_row = {"nn_id": 2, "dc_id": 2, "nn_email": 2, "dc_email": 2}
        samples = [(1, "a@b.com"), (2, "c@d.com")]

        cursor = self._make_cursor(
            table_names=["widgets"],
            columns_by_table=columns,
            foreign_keys=[],
            row_counts=2,
            stats_row=stats_row,
            sample_rows=samples,
        )

        connection = MagicMock()
        connection.cursor.return_value = cursor
        mock_connect.return_value = connection

        result = scan_mysql_source({
            "host": "localhost",
            "port": 3306,
            "database": "app_db",
            "user": "root",
            "password": "secret",
        })

        self.assertEqual(len(result["datasets"]), 1)
        dataset = result["datasets"][0]
        self.assertEqual(dataset["schema_name"], "app_db")
        self.assertEqual(dataset["table_name"], "widgets")
        self.assertEqual(dataset["row_count"], 2)
        self.assertEqual(dataset["column_stats"]["email"], {"non_null": 2, "distinct": 2})
        self.assertIn("a@b.com", dataset["column_samples"]["email"])
        self.assertEqual(result["foreign_keys"], [])

    @patch("app.connectors.mysql_scanner.pymysql.connect")
    def test_connection_failure_raises_operational_error(self, mock_connect):
        import pymysql

        mock_connect.side_effect = pymysql.err.OperationalError("connection refused")

        with self.assertRaises(pymysql.err.OperationalError):
            scan_mysql_source({
                "host": "unreachable",
                "port": 3306,
                "database": "app_db",
                "user": "root",
                "password": "secret",
            })


if __name__ == "__main__":
    unittest.main()
