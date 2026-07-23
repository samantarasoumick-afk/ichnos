"""
Unit tests for app/connectors/snowflake_scanner.py against a mocked
snowflake.connector connection/cursor - there's no live Snowflake
account in this environment, so these test the query-shaping and
result-assembly logic (identifier quoting, schema scoping, the
tables/columns/foreign-keys queries, row/column stat collection) in
isolation, the same way postgres_scanner/mysql_scanner are tested.
"""

import unittest
from unittest.mock import MagicMock, patch

from app.connectors.snowflake_scanner import _quote_ident, scan_snowflake_source


class QuoteIdentTests(unittest.TestCase):

    def test_wraps_in_double_quotes(self):
        self.assertEqual(_quote_ident("CUSTOMERS"), '"CUSTOMERS"')

    def test_escapes_embedded_double_quote(self):
        self.assertEqual(_quote_ident('weird"name'), '"weird""name"')


class ScanSnowflakeSourceTests(unittest.TestCase):

    def _make_cursor(self, table_names, columns_by_table, foreign_keys, row_counts, stats_row, sample_rows):
        """
        Same driving-by-last-query approach as test_mysql_scanner.py's
        mock cursor, matching the query sequence
        scan_snowflake_source actually issues: tables list, FK list,
        then per-table (columns, row count, stats, samples).
        """

        cursor = MagicMock()
        call_log = {}

        def execute(query, params=None):
            call_log["last_query"] = query.strip()

        def fetchall():
            q = call_log["last_query"]
            if "FROM information_schema.tables" in q:
                return [(schema, name) for schema, name in table_names]
            if "FROM information_schema.referential_constraints" in q:
                return foreign_keys
            if "FROM information_schema.columns" in q:
                return columns_by_table
            if q.startswith('SELECT "'):
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

    @patch("app.connectors.snowflake_scanner.snowflake.connector.connect")
    def test_scan_returns_expected_shape_for_single_table(self, mock_connect):
        columns = [("ID", "NUMBER", "NO"), ("EMAIL", "TEXT", "YES")]
        stats_row = {"NN_ID": 2, "DC_ID": 2, "NN_EMAIL": 2, "DC_EMAIL": 2}
        samples = [(1, "a@b.com"), (2, "c@d.com")]

        cursor = self._make_cursor(
            table_names=[("PUBLIC", "CUSTOMERS")],
            columns_by_table=columns,
            foreign_keys=[],
            row_counts=2,
            stats_row=stats_row,
            sample_rows=samples,
        )

        connection = MagicMock()
        connection.cursor.return_value = cursor
        mock_connect.return_value = connection

        result = scan_snowflake_source({
            "account": "xy12345",
            "user": "svc_user",
            "password": "secret",
            "warehouse": "COMPUTE_WH",
            "database": "APP_DB",
        })

        self.assertEqual(len(result["datasets"]), 1)
        dataset = result["datasets"][0]
        self.assertEqual(dataset["schema_name"], "PUBLIC")
        self.assertEqual(dataset["table_name"], "CUSTOMERS")
        self.assertEqual(dataset["row_count"], 2)
        self.assertEqual(dataset["column_stats"]["EMAIL"], {"non_null": 2, "distinct": 2})
        self.assertIn("a@b.com", dataset["column_samples"]["EMAIL"])
        self.assertEqual(result["foreign_keys"], [])

    @patch("app.connectors.snowflake_scanner.snowflake.connector.connect")
    def test_schema_filter_scopes_the_tables_query(self, mock_connect):
        columns = [("ID", "NUMBER", "NO")]
        stats_row = {"NN_ID": 1, "DC_ID": 1}
        samples = [(1,)]

        cursor = self._make_cursor(
            table_names=[("SALES", "ORDERS")],
            columns_by_table=columns,
            foreign_keys=[],
            row_counts=1,
            stats_row=stats_row,
            sample_rows=samples,
        )

        connection = MagicMock()
        connection.cursor.return_value = cursor
        mock_connect.return_value = connection

        result = scan_snowflake_source({
            "account": "xy12345",
            "user": "svc_user",
            "password": "secret",
            "warehouse": "COMPUTE_WH",
            "database": "APP_DB",
            "schema": "SALES",
        })

        self.assertEqual(result["datasets"][0]["schema_name"], "SALES")
        mock_connect.assert_called_once()
        _, kwargs = mock_connect.call_args
        self.assertEqual(kwargs["schema"], "SALES")

    @patch("app.connectors.snowflake_scanner.snowflake.connector.connect")
    def test_foreign_key_query_failure_does_not_fail_the_scan(self, mock_connect):
        columns = [("ID", "NUMBER", "NO")]
        stats_row = {"NN_ID": 1, "DC_ID": 1}
        samples = [(1,)]

        cursor = self._make_cursor(
            table_names=[("PUBLIC", "WIDGETS")],
            columns_by_table=columns,
            foreign_keys=[],
            row_counts=1,
            stats_row=stats_row,
            sample_rows=samples,
        )

        # Make the FK query specifically raise, while everything else
        # still works - simulates a role that can't see constraint
        # metadata views.
        real_execute = cursor.execute.side_effect

        def execute_with_fk_failure(query, params=None):
            if "referential_constraints" in query:
                raise Exception("insufficient privileges")
            return real_execute(query, params)

        cursor.execute.side_effect = execute_with_fk_failure

        connection = MagicMock()
        connection.cursor.return_value = cursor
        mock_connect.return_value = connection

        result = scan_snowflake_source({
            "account": "xy12345",
            "user": "svc_user",
            "password": "secret",
            "warehouse": "COMPUTE_WH",
            "database": "APP_DB",
        })

        self.assertEqual(result["foreign_keys"], [])
        self.assertEqual(len(result["datasets"]), 1)

    @patch("app.connectors.snowflake_scanner.snowflake.connector.connect")
    def test_connection_failure_raises_operational_error(self, mock_connect):
        import snowflake.connector.errors

        mock_connect.side_effect = snowflake.connector.errors.OperationalError(
            msg="connection refused"
        )

        with self.assertRaises(snowflake.connector.errors.OperationalError):
            scan_snowflake_source({
                "account": "unreachable",
                "user": "svc_user",
                "password": "secret",
                "warehouse": "COMPUTE_WH",
                "database": "APP_DB",
            })


if __name__ == "__main__":
    unittest.main()
