"""
Azure SQL Database / Azure Synapse (dedicated SQL pool) scanner - same
dataset_info contract as postgres_scanner.py (see that file for the
canonical shape). Both are T-SQL engines (the SQL Server family), so
this uses pymssql rather than pyodbc - pymssql bundles FreeTDS, so it
doesn't require a system-level ODBC driver to be installed separately,
unlike pyodbc.

T-SQL differs from Postgres/MySQL in two ways this file has to work
around: identifiers are bracket-quoted ([schema].[table], not
double/back-quoted), and row-limiting uses SELECT TOP N instead of a
trailing LIMIT N. Its INFORMATION_SCHEMA views (including
CONSTRAINT_COLUMN_USAGE, used for foreign keys below) otherwise follow
the same ANSI-standard shape Postgres implements.

connection_config keys: host, port (defaults to 1433), database,
user, password.
"""

import pymssql


SAMPLE_SIZE = 20

DEFAULT_PORT = 1433


def _quote_ident(name: str) -> str:
    """
    T-SQL identifier quoting uses square brackets - a literal closing
    bracket inside a name is escaped by doubling it, the same
    convention SQL Server itself uses.
    """

    return "[" + name.replace("]", "]]") + "]"


def _sample_and_profile_table(cursor, schema_name: str, table_name: str, columns: list[tuple]):
    """
    Same contract as postgres_scanner._sample_and_profile_table: for
    one table, collect row_count, per-column non-null/distinct counts,
    and up to SAMPLE_SIZE sampled values per column.
    """

    table_ident = f"{_quote_ident(schema_name)}.{_quote_ident(table_name)}"

    cursor.execute(f"SELECT COUNT(*) FROM {table_ident}")
    row_count = cursor.fetchone()[0]

    column_stats = {}

    if row_count > 0 and columns:

        count_exprs = []

        for column_name, _data_type, _nullable in columns:
            col_ident = _quote_ident(column_name)
            count_exprs.append(
                f"COUNT({col_ident}) AS {_quote_ident('nn_' + column_name)}, "
                f"COUNT(DISTINCT {col_ident}) AS {_quote_ident('dc_' + column_name)}"
            )

        stats_query = f"SELECT {', '.join(count_exprs)} FROM {table_ident}"

        try:
            cursor.execute(stats_query)
            row = cursor.fetchone()
            colnames = [desc[0] for desc in cursor.description]
            stats_row = dict(zip(colnames, row))

            for column_name, _data_type, _nullable in columns:
                column_stats[column_name] = {
                    "non_null": stats_row.get(f"nn_{column_name}", 0),
                    "distinct": stats_row.get(f"dc_{column_name}", 0),
                }

        except Exception:
            # A single unusual column type shouldn't fail the whole
            # scan - fall back to "unknown" stats for this table.
            for column_name, _data_type, _nullable in columns:
                column_stats[column_name] = {"non_null": None, "distinct": None}

    column_samples = {column_name: [] for column_name, _dt, _n in columns}

    if row_count > 0 and columns:

        select_cols = ", ".join(_quote_ident(column_name) for column_name, _dt, _n in columns)

        sample_query = f"SELECT TOP {int(SAMPLE_SIZE)} {select_cols} FROM {table_ident}"

        try:
            cursor.execute(sample_query)
            rows = cursor.fetchall()

            for row in rows:
                for (column_name, _dt, _n), value in zip(columns, row):
                    if value is not None:
                        column_samples[column_name].append(str(value))

        except Exception:
            pass

    return row_count, column_stats, column_samples


def scan_azure_sql_source(config: dict):

    try:
        connection = pymssql.connect(
            server=config["host"],
            port=str(config.get("port") or DEFAULT_PORT),
            database=config["database"],
            user=config["user"],
            password=config["password"],
        )
    except pymssql.OperationalError as exc:
        raise pymssql.OperationalError(
            f"Unable to connect to Azure SQL: {exc}"
        ) from exc

    cursor = connection.cursor()

    cursor.execute(
        """
        SELECT TABLE_SCHEMA, TABLE_NAME
        FROM INFORMATION_SCHEMA.TABLES
        WHERE TABLE_TYPE = 'BASE TABLE'
        """
    )

    tables = cursor.fetchall()

    foreign_keys = []

    try:
        cursor.execute("""
        SELECT
            tc.TABLE_SCHEMA,
            tc.TABLE_NAME,
            kcu.COLUMN_NAME,
            ccu.TABLE_SCHEMA AS FOREIGN_SCHEMA,
            ccu.TABLE_NAME AS FOREIGN_TABLE,
            ccu.COLUMN_NAME AS FOREIGN_COLUMN
        FROM INFORMATION_SCHEMA.TABLE_CONSTRAINTS tc
        JOIN INFORMATION_SCHEMA.KEY_COLUMN_USAGE kcu
            ON tc.CONSTRAINT_NAME = kcu.CONSTRAINT_NAME
        JOIN INFORMATION_SCHEMA.REFERENTIAL_CONSTRAINTS rc
            ON tc.CONSTRAINT_NAME = rc.CONSTRAINT_NAME
        JOIN INFORMATION_SCHEMA.CONSTRAINT_COLUMN_USAGE ccu
            ON rc.UNIQUE_CONSTRAINT_NAME = ccu.CONSTRAINT_NAME
        WHERE tc.CONSTRAINT_TYPE = 'FOREIGN KEY'
        """)
        foreign_keys = cursor.fetchall()
    except Exception:
        # Synapse dedicated SQL pools in particular often don't
        # support (or the connecting login can't see) the full
        # constraint-view chain - the rest of the scan shouldn't fail
        # just because foreign keys aren't visible.
        foreign_keys = []

    datasets = []

    for schema_name, table_name in tables:

        cursor.execute(
            """
            SELECT
                COLUMN_NAME,
                DATA_TYPE,
                IS_NULLABLE
            FROM INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_SCHEMA = %s
            AND TABLE_NAME = %s
            ORDER BY ORDINAL_POSITION
            """,
            (schema_name, table_name)
        )

        columns = cursor.fetchall()

        row_count, column_stats, column_samples = _sample_and_profile_table(
            cursor, schema_name, table_name, columns
        )

        datasets.append({
            "schema_name": schema_name,
            "table_name": table_name,
            "columns": columns,
            "row_count": row_count,
            "column_stats": column_stats,
            "column_samples": column_samples,
        })

    cursor.close()
    connection.close()

    return {
        "datasets": datasets,
        "foreign_keys": foreign_keys,
    }
