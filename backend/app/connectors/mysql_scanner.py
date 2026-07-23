import pymysql
import pymysql.cursors


SAMPLE_SIZE = 20


def _quote_ident(name: str) -> str:
    """
    MySQL identifier quoting uses backticks, not the double quotes
    Postgres uses - a literal backtick inside a name (rare, but valid)
    is escaped by doubling it, same convention MySQL itself uses.
    """

    return "`" + name.replace("`", "``") + "`"


def _sample_and_profile_table(cursor, schema_name: str, table_name: str, columns: list[tuple]):
    """
    Same contract as postgres_scanner._sample_and_profile_table: for
    one table, collect row_count, per-column non-null/distinct counts,
    and up to SAMPLE_SIZE sampled values per column - so the privacy
    engine and data quality service (which only know about that shared
    contract, not which database produced it) work unchanged.
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


def scan_mysql_source(config: dict):
    """
    Same return contract as scan_postgres_source:
    {"datasets": [{"schema_name", "table_name", "columns", "row_count",
    "column_stats", "column_samples"}, ...], "foreign_keys": [...]}

    MySQL doesn't distinguish "database" from "schema" the way Postgres
    does - a MySQL "database" IS the schema, and a connection is
    already scoped to one. So schema_name below is always the
    connected database name, and this scans every table in it (no
    equivalent of Postgres's "all schemas in this database" sweep,
    because there's nothing further to sweep).
    """

    try:
        connection = pymysql.connect(
            host=config["host"],
            port=int(config.get("port", 3306)),
            database=config["database"],
            user=config["user"],
            password=config["password"],
            cursorclass=pymysql.cursors.Cursor,
        )
    except pymysql.err.OperationalError as exc:
        raise pymysql.err.OperationalError(
            f"Unable to connect to MySQL: {exc}"
        ) from exc

    cursor = connection.cursor()
    schema_name = config["database"]

    cursor.execute(
        """
        SELECT table_name
        FROM information_schema.tables
        WHERE table_schema = %s
        AND table_type = 'BASE TABLE'
        """,
        (schema_name,)
    )

    tables = [row[0] for row in cursor.fetchall()]

    # Unlike Postgres, MySQL's key_column_usage already carries the
    # referenced (foreign) table/column directly - no join through a
    # separate constraint_column_usage view needed.
    cursor.execute(
        """
        SELECT
            table_schema,
            table_name,
            column_name,
            referenced_table_schema,
            referenced_table_name,
            referenced_column_name
        FROM information_schema.key_column_usage
        WHERE table_schema = %s
        AND referenced_table_name IS NOT NULL
        """,
        (schema_name,)
    )

    foreign_keys = cursor.fetchall()

    datasets = []

    for table_name in tables:

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
