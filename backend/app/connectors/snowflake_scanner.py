"""
Snowflake scanner - same dataset_info contract as postgres_scanner.py
(see that file for the canonical shape). Snowflake's INFORMATION_SCHEMA
is modeled closely on the ANSI-standard schema Postgres also uses, so
this mirrors postgres_scanner's structure rather than mysql_scanner's:
one connection can see multiple schemas within a database, same as
Postgres, unlike MySQL where a connection is already scoped to one
schema.

connection_config keys:
  - account (required): the Snowflake account identifier, e.g.
    "xy12345.us-east-1" or "myorg-myaccount"
  - user, password (required)
  - warehouse (required): the compute warehouse to run queries on
  - database (required)
  - schema (optional): scan only this schema; if omitted, every
    schema in the database is scanned (except INFORMATION_SCHEMA)
  - role (optional)
"""

import snowflake.connector
import snowflake.connector.errors


SAMPLE_SIZE = 20


def _quote_ident(name: str) -> str:
    """
    Snowflake identifier quoting uses double quotes, same convention
    as Postgres - a literal double quote inside a name is escaped by
    doubling it.
    """

    return '"' + name.replace('"', '""') + '"'


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
                f'COUNT({col_ident}) AS {_quote_ident("nn_" + column_name)}, '
                f'COUNT(DISTINCT {col_ident}) AS {_quote_ident("dc_" + column_name)}'
            )

        stats_query = f"SELECT {', '.join(count_exprs)} FROM {table_ident}"

        try:
            cursor.execute(stats_query)
            row = cursor.fetchone()
            colnames = [desc[0] for desc in cursor.description]
            stats_row = dict(zip(colnames, row))

            for column_name, _data_type, _nullable in columns:
                # Snowflake upper-cases unquoted result column aliases,
                # so look up case-insensitively rather than assuming
                # the alias comes back exactly as written.
                nn_key = next(
                    (k for k in stats_row if k.lower() == f"nn_{column_name}".lower()),
                    None
                )
                dc_key = next(
                    (k for k in stats_row if k.lower() == f"dc_{column_name}".lower()),
                    None
                )
                column_stats[column_name] = {
                    "non_null": stats_row.get(nn_key, 0) if nn_key else 0,
                    "distinct": stats_row.get(dc_key, 0) if dc_key else 0,
                }

        except Exception:
            # A single unusual column type shouldn't fail the whole
            # scan - fall back to "unknown" stats for this table.
            for column_name, _data_type, _nullable in columns:
                column_stats[column_name] = {"non_null": None, "distinct": None}

    column_samples = {column_name: [] for column_name, _dt, _n in columns}

    if row_count > 0 and columns:

        select_cols = ", ".join(_quote_ident(column_name) for column_name, _dt, _n in columns)

        sample_query = f"SELECT {select_cols} FROM {table_ident} LIMIT {int(SAMPLE_SIZE)}"

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


def scan_snowflake_source(config: dict):

    try:
        connection = snowflake.connector.connect(
            account=config["account"],
            user=config["user"],
            password=config["password"],
            warehouse=config["warehouse"],
            database=config["database"],
            schema=config.get("schema") or None,
            role=config.get("role") or None,
        )
    except snowflake.connector.errors.OperationalError as exc:
        raise snowflake.connector.errors.OperationalError(
            msg=f"Unable to connect to Snowflake: {exc}"
        ) from exc

    cursor = connection.cursor()

    schema_filter = config.get("schema")

    if schema_filter:
        cursor.execute(
            """
            SELECT table_schema, table_name
            FROM information_schema.tables
            WHERE table_type = 'BASE TABLE'
            AND table_schema = %s
            """,
            (schema_filter,)
        )
    else:
        cursor.execute(
            """
            SELECT table_schema, table_name
            FROM information_schema.tables
            WHERE table_type = 'BASE TABLE'
            AND table_schema != 'INFORMATION_SCHEMA'
            """
        )

    tables = cursor.fetchall()

    foreign_keys = []

    try:
        cursor.execute(
            """
            SELECT
                kcu.table_schema,
                kcu.table_name,
                kcu.column_name,
                ccu.table_schema AS foreign_schema,
                ccu.table_name AS foreign_table,
                ccu.column_name AS foreign_column
            FROM information_schema.referential_constraints rc
            JOIN information_schema.key_column_usage kcu
                ON kcu.constraint_name = rc.constraint_name
                AND kcu.constraint_schema = rc.constraint_schema
            JOIN information_schema.key_column_usage ccu
                ON ccu.constraint_name = rc.unique_constraint_name
                AND ccu.constraint_schema = rc.unique_constraint_schema
            """
        )
        foreign_keys = cursor.fetchall()
    except Exception:
        # Foreign keys are informational-only in Snowflake and rarely
        # declared - if this account/role can't see the constraint
        # views for any reason, the rest of the scan shouldn't fail.
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
            ORDER BY ordinal_position
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
