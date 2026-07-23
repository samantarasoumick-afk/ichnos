import psycopg2
from psycopg2 import sql


SAMPLE_SIZE = 20


def _sample_and_profile_table(cursor, schema_name: str, table_name: str, columns: list[tuple]):
    """
    For one table, in a small number of queries, collect:
      - row_count: total rows
      - column_stats: {col_name: {"non_null": int, "distinct": int}}
      - column_samples: {col_name: [str, ...]} up to SAMPLE_SIZE values

    Built with psycopg2.sql.Identifier so column/table names (which
    come from information_schema, not user input, but are still
    interpolated into SQL) are safely quoted rather than f-string'd
    into the query.
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
            # A single unusual column type (e.g. one Postgres can't
            # run COUNT(DISTINCT ...) on cheaply) shouldn't fail the
            # whole scan - fall back to "unknown" stats for this table.
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


def scan_postgres_source(config: dict):

    try:
        connection = psycopg2.connect(
            host=config["host"],
            port=config["port"],
            database=config["database"],
            user=config["user"],
            password=config["password"]
        )
    except psycopg2.OperationalError as exc:
        raise psycopg2.OperationalError(
            f"Unable to connect to PostgreSQL: {exc}"
        ) from exc

    cursor = connection.cursor()

    cursor.execute(
        """
        SELECT table_schema, table_name
        FROM information_schema.tables
        WHERE table_schema NOT IN (
            'information_schema',
            'pg_catalog'
        )
        """
    )

    tables = cursor.fetchall()

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
