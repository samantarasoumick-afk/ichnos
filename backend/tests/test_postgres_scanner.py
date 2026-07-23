import unittest
from unittest.mock import patch

import psycopg2

from app.connectors.postgres_scanner import scan_postgres_source


class PostgresScannerTests(unittest.TestCase):
    @patch("app.connectors.postgres_scanner.psycopg2.connect")
    def test_scan_postgres_source_raises_clear_error_when_connection_fails(self, mock_connect):
        mock_connect.side_effect = psycopg2.OperationalError("connection refused")

        with self.assertRaises(psycopg2.OperationalError) as context:
            scan_postgres_source({
                "host": "localhost",
                "port": 5432,
                "database": "metadata",
                "user": "admin",
                "password": "admin",
            })

        self.assertIn("Unable to connect to PostgreSQL", str(context.exception))


if __name__ == "__main__":
    unittest.main()
