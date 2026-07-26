"""
Dispatch table from Source.type to a scanner function. Every scanner
shares the same contract: scanner(connection_config: dict) -> {
"datasets": [...], "foreign_keys": [...]} - see postgres_scanner.py
for the full shape each dataset entry follows.

Previously the scan and lineage-discovery endpoints each hardcoded a
call to scan_postgres_source() regardless of what Source.type actually
said, so creating a "mysql" or "snowflake" source and scanning it
either crashed or silently ran Postgres-specific queries against the
wrong database. Centralizing the dispatch here means adding a new
connector is one entry in SCANNERS, not another set of hardcoded
branches in every endpoint that scans something.
"""

import psycopg2
import pymysql
import pymssql
import snowflake.connector.errors
from botocore.exceptions import BotoCoreError, ClientError

from app.connectors.postgres_scanner import scan_postgres_source
from app.connectors.mysql_scanner import scan_mysql_source
from app.connectors.snowflake_scanner import scan_snowflake_source
from app.connectors.redshift_scanner import scan_redshift_source
from app.connectors.s3_scanner import scan_s3_source
from app.connectors.azure_sql_scanner import scan_azure_sql_source
from app.connectors.stripe_scanner import scan_stripe_source, StripeConnectionError


SCANNERS = {
    "postgres": scan_postgres_source,
    "postgresql": scan_postgres_source,
    "mysql": scan_mysql_source,
    "mariadb": scan_mysql_source,
    "snowflake": scan_snowflake_source,
    "redshift": scan_redshift_source,
    "s3": scan_s3_source,
    "azure_sql": scan_azure_sql_source,
    "synapse": scan_azure_sql_source,
    "stripe": scan_stripe_source,
}

# Connection-failure exception types across every supported driver,
# so callers can catch "the source was unreachable" generically
# without knowing which driver produced the error.
CONNECTION_ERRORS = (
    psycopg2.OperationalError,
    pymysql.err.OperationalError,
    snowflake.connector.errors.OperationalError,
    pymssql.OperationalError,
    ClientError,
    BotoCoreError,
    StripeConnectionError,
)


def get_scanner(source_type: str):
    return SCANNERS.get((source_type or "").strip().lower())


def supported_types() -> list[str]:
    return sorted(SCANNERS.keys())
