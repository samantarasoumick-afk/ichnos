"""
Tests for the scanner dispatch registry (app/connectors/registry.py)
and its use from the scan/lineage-discovery endpoints. Before this
existed, both endpoints hardcoded a call to scan_postgres_source()
regardless of Source.type, so creating a "mysql" source and scanning
it would run Postgres-specific queries against a MySQL connection
(psycopg2.connect against a MySQL host) rather than failing cleanly
or actually scanning it.
"""

import unittest
import uuid
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.connectors.registry import get_scanner, supported_types
from app.connectors.postgres_scanner import scan_postgres_source
from app.connectors.mysql_scanner import scan_mysql_source
from app.connectors.snowflake_scanner import scan_snowflake_source
from app.connectors.redshift_scanner import scan_redshift_source
from app.connectors.s3_scanner import scan_s3_source
from app.connectors.azure_sql_scanner import scan_azure_sql_source
from app.main import app


MYSQL_SCAN_RESULT = {
    "datasets": [{
        "schema_name": "app_db",
        "table_name": "widgets",
        "columns": [
            ("id", "int", "NO"),
            ("email", "varchar", "YES"),
        ],
        "row_count": 2,
        "column_stats": {
            "id": {"non_null": 2, "distinct": 2},
            "email": {"non_null": 2, "distinct": 2},
        },
        "column_samples": {
            "id": ["1", "2"],
            "email": ["a@b.com", "c@d.com"],
        },
    }],
    "foreign_keys": [],
}

SNOWFLAKE_SCAN_RESULT = {
    "datasets": [{
        "schema_name": "PUBLIC",
        "table_name": "CUSTOMERS",
        "columns": [
            ("ID", "NUMBER", "NO"),
            ("EMAIL", "TEXT", "YES"),
        ],
        "row_count": 2,
        "column_stats": {
            "ID": {"non_null": 2, "distinct": 2},
            "EMAIL": {"non_null": 2, "distinct": 2},
        },
        "column_samples": {
            "ID": ["1", "2"],
            "EMAIL": ["a@b.com", "c@d.com"],
        },
    }],
    "foreign_keys": [],
}


class ScannerRegistryUnitTests(unittest.TestCase):

    def test_known_types_resolve_to_the_right_scanner(self):
        self.assertIs(get_scanner("postgres"), scan_postgres_source)
        self.assertIs(get_scanner("postgresql"), scan_postgres_source)
        self.assertIs(get_scanner("mysql"), scan_mysql_source)
        self.assertIs(get_scanner("mariadb"), scan_mysql_source)
        self.assertIs(get_scanner("snowflake"), scan_snowflake_source)
        self.assertIs(get_scanner("redshift"), scan_redshift_source)
        self.assertIs(get_scanner("s3"), scan_s3_source)
        self.assertIs(get_scanner("azure_sql"), scan_azure_sql_source)
        self.assertIs(get_scanner("synapse"), scan_azure_sql_source)

    def test_lookup_is_case_and_whitespace_insensitive(self):
        self.assertIs(get_scanner("MySQL"), scan_mysql_source)
        self.assertIs(get_scanner("  postgresql  "), scan_postgres_source)
        self.assertIs(get_scanner("  Snowflake  "), scan_snowflake_source)

    def test_unknown_type_resolves_to_none(self):
        self.assertIsNone(get_scanner("oracle"))
        self.assertIsNone(get_scanner(""))
        self.assertIsNone(get_scanner(None))

    def test_supported_types_lists_everything_registered(self):
        types = supported_types()
        self.assertIn("postgres", types)
        self.assertIn("mysql", types)
        self.assertIn("snowflake", types)
        self.assertIn("redshift", types)
        self.assertIn("s3", types)
        self.assertIn("azure_sql", types)


class ScannerDispatchApiTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)

    def setUp(self):
        self._n = uuid.uuid4().hex[:8]

        r = self.client.post("/api/auth/register", json={
            "email": f"reg{self._n}@a.com",
            "password": "password123",
            "organization_name": f"Registry Org {self._n}",
        })
        self.assertEqual(r.status_code, 200, r.text)

        r = self.client.post("/api/auth/login", json={
            "email": f"reg{self._n}@a.com",
            "password": "password123",
        })
        self.headers = {"Authorization": f"Bearer {r.json()['access_token']}"}

    def test_unsupported_source_type_returns_400(self):
        r = self.client.post("/api/sources", headers=self.headers, json={
            "name": f"Oracle Source {self._n}",
            "type": "oracle",
            "connection_config": {"host": "x"},
        })
        source_id = r.json()["id"]

        r = self.client.post(f"/api/scanner/{source_id}", headers=self.headers)
        self.assertEqual(r.status_code, 400)
        self.assertIn("not yet supported", r.json()["detail"])

    @patch("app.api.scanner.get_scanner")
    def test_mysql_source_scans_through_the_dispatch(self, mock_get_scanner):
        mock_get_scanner.return_value = lambda config: MYSQL_SCAN_RESULT

        r = self.client.post("/api/sources", headers=self.headers, json={
            "name": f"MySQL Source {self._n}",
            "type": "mysql",
            "connection_config": {"host": "x", "database": "app_db", "user": "u", "password": "p"},
        })
        source_id = r.json()["id"]

        r = self.client.post(f"/api/scanner/{source_id}", headers=self.headers)
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["datasets_discovered"], 1)

        r = self.client.get("/api/datasets", headers=self.headers)
        datasets = r.json()
        self.assertEqual(len(datasets), 1)
        self.assertEqual(datasets[0]["schema_name"], "app_db")
        self.assertEqual(datasets[0]["name"], "widgets")

    @patch("app.api.scanner.get_scanner")
    def test_snowflake_source_scans_through_the_dispatch(self, mock_get_scanner):
        mock_get_scanner.return_value = lambda config: SNOWFLAKE_SCAN_RESULT

        r = self.client.post("/api/sources", headers=self.headers, json={
            "name": f"Snowflake Source {self._n}",
            "type": "snowflake",
            "connection_config": {
                "account": "xy12345",
                "user": "u",
                "password": "p",
                "warehouse": "COMPUTE_WH",
                "database": "APP_DB",
            },
        })
        source_id = r.json()["id"]

        r = self.client.post(f"/api/scanner/{source_id}", headers=self.headers)
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["datasets_discovered"], 1)

        r = self.client.get("/api/datasets", headers=self.headers)
        datasets = r.json()
        self.assertEqual(len(datasets), 1)
        self.assertEqual(datasets[0]["schema_name"], "PUBLIC")
        self.assertEqual(datasets[0]["name"], "CUSTOMERS")

    @patch("app.api.scanner.get_scanner")
    def test_s3_source_scans_through_the_dispatch(self, mock_get_scanner):
        s3_scan_result = {
            "datasets": [{
                "schema_name": "my-bucket",
                "table_name": "orders",
                "columns": [("id", "integer", "NO")],
                "row_count": 2,
                "column_stats": {"id": {"non_null": 2, "distinct": 2}},
                "column_samples": {"id": ["1", "2"]},
            }],
            "foreign_keys": [],
        }
        mock_get_scanner.return_value = lambda config: s3_scan_result

        r = self.client.post("/api/sources", headers=self.headers, json={
            "name": f"S3 Source {self._n}",
            "type": "s3",
            "connection_config": {"bucket": "my-bucket", "prefix": "orders/"},
        })
        source_id = r.json()["id"]

        r = self.client.post(f"/api/scanner/{source_id}", headers=self.headers)
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["datasets_discovered"], 1)

        r = self.client.get("/api/datasets", headers=self.headers)
        datasets = r.json()
        self.assertEqual(len(datasets), 1)
        self.assertEqual(datasets[0]["schema_name"], "my-bucket")
        self.assertEqual(datasets[0]["name"], "orders")


if __name__ == "__main__":
    unittest.main()
