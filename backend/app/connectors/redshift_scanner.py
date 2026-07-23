"""
Redshift scanner - same dataset_info contract as postgres_scanner.py
(see that file for the canonical shape). Amazon Redshift is wire- and
catalog-compatible with Postgres 8.x, so this reuses psycopg2 (already
a dependency for the Postgres connector) rather than pulling in a
Redshift-specific driver, and mirrors postgres_scanner's structure
almost exactly. The one default worth calling out: Redshift clusters
listen on port 5439, not Postgres's 5432.

connection_config keys: host, port (defaults to 5439 if omitted),
database, user, password.
"""

import psycopg2
from psycopg2 import sql


SAMPLE_SIZE = 20

DEFAULT_PORT = 5439


def _sample_and_profile_table(cursor, schema_name: str, table_name: str, columns: list[tuple]):
    """
    Same contract as postgres_scanner._sample_and_profile_table: for
    one table, collect row_count, per-column non-null/distinct counts,
    and up to SAMPLE_SIZE sampled values per column.
    """

    table_ident = sql.SQL(".").join([
        sql.Identifier(schema_name),
        sql.Identifier(table_name),
    ])

    cursor.execute(
        sql.SQL("SELECT COUNT(*) FROM {}").format(table_ident)
    )
    row_count = cursor.fetchone()[0]

    column_stats = {}

    if row_count > 0 and columns:

        count_exprs = []

        for column_name, _data_type, _nullable in columns:
            count_exprs.append(
                sql.SQL("COUNT({0}) AS {1}, COUNT(DISTINCT {0}) AS {2}").format(
                    sql.Identifier(column_name),
                    sql.Identifier(f"nn_{column_name}"),
                    sql.Identifier(f"dc_{column_name}"),
                )
            )

        stats_query = sql.SQL("SELECT {} FROM {}").format(
            sql.SQL(", ").join(count_exprs),
            table_ident,
        )

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
            # A single unusual column type (Redshift has a few types
            # Postgres doesn't, e.g. SUPER) shouldn't fail the whole
            # scan - fall back to "unknown" stats for this table.
            for column_name, _data_type, _nullable in columns:
                column_stats[column_name] = {"non_null": None, "distinct": None}

    column_samples = {column_name: [] for column_name, _dt, _n in columns}

    if row_count > 0 and columns:

        select_cols = sql.SQL(", ").join(
            sql.Identifier(column_name) for column_name, _dt, _n in columns
        )

        sample_query = sql.SQL("SELECT {} FROM {} LIMIT {}").format(
            select_cols,
            table_ident,
            sql.Literal(SAMPLE_SIZE),
        )

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


def scan_redshift_source(config: dict):

    try:
        connection = psycopg2.connect(
            host=config["host"],
            port=int(config.get("port") or DEFAULT_PORT),
            database=config["database"],
            user=config["user"],
            password=config["password"]
        )
    except psycopg2.OperationalError as exc:
        raise psycopg2.OperationalError(
            f"Unable to connect to Redshift: {exc}"
        ) from exc

    cursor = connection.cursor()

    cursor.execute(
        """
        SELECT table_schema, table_name
        FROM information_schema.tables
        WHERE table_schema NOT IN (
            'information_schema',
            'pg_catalog',
            'pg_internal'
        )
        AND table_type = 'BASE TABLE'
        """
    )

    tables = cursor.fetchall()

    # Redshift's constraint views work the same way Postgres's do, but
    # unlike Postgres, foreign keys there are informational-only and
    # not enforced - many clusters have none declared at all, so this
    # is wrapped defensively rather than assumed to always succeed.
    foreign_keys = []

    try:
        cursor.execute("""
        SELECT
            tc.table_schema,
            tc.table_name,
            kcu.column_name,
            ccu.table_schema AS foreign_schema,
            ccu.table_name AS foreign_table,
            ccu.column_name AS foreign_column
        FROM information_schema.table_constraints tc
        JOIN information_schema.key_column_usage kcu
            ON tc.constraint_name = kcu.constraint_name
        JOIN information_schema.constraint_column_usage ccu
            ON ccu.constraint_name = tc.constraint_name
        WHERE tc.constraint_type='FOREIGN KEY';
        """)
        foreign_keys = cursor.fetchall()
    except Exception:
        foreign_keys = []

    datasets = []

    for schema_name, table_name in tables:

        cursor.execute(
            """
            SELECT
                column_name,
                data_type,
                is_nullable
            FROM information_schema.columns
            WHERE table_schema = %s
            AND table_name = %s
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
