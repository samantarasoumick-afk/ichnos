"""
Parses an uploaded CSV file into the same dataset_info contract every
live-database scanner produces (see postgres_scanner.py for the
canonical shape) - so a file upload flows through the exact same
column classification, data quality profiling, and governance
pipeline as a live scan. This exists for orgs that can't (or won't
yet) hand over live database credentials: a firewalled on-prem
database, a pilot that isn't ready to grant access, or data that
simply lives as an export rather than in a queryable database.

No new dependency: CSV parsing is stdlib-only. Excel (.xlsx) isn't
supported yet - see the note on parse_upload for where to add it.
"""

import csv
import io


SAMPLE_SIZE = 20

# A sanity cap, not a hard product limit - protects against a
# pathological upload (a multi-GB "CSV") from parsing the entire file
# into memory before anyone notices something's wrong.
MAX_ROWS = 50_000


def _looks_like_int(value: str) -> bool:
    try:
        int(value)
        return True
    except ValueError:
        return False


def _looks_like_float(value: str) -> bool:
    try:
        float(value)
        return True
    except ValueError:
        return False


def _infer_data_type(values: list[str]) -> str:

    if not values:
        return "varchar"

    if all(_looks_like_int(v) for v in values):
        return "integer"

    if all(_looks_like_float(v) for v in values):
        return "numeric"

    return "varchar"


def parse_csv_upload(file_bytes: bytes, table_name: str, schema_name: str = "uploads") -> dict:
    """
    Raises ValueError (not an HTTP-aware exception - the caller
    translates that to a 400) for anything wrong with the file itself:
    undecodable bytes, no header row, no data rows.
    """

    try:
        text = file_bytes.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ValueError(
            "Unable to read this file as UTF-8 text. Please upload a UTF-8 encoded CSV."
        ) from exc

    reader = csv.reader(io.StringIO(text))

    try:
        header = next(reader)
    except StopIteration:
        raise ValueError("The file is empty.")

    header = [name.strip() for name in header if name.strip()]

    if not header:
        raise ValueError("No column headers were found in the first row.")

    if len(header) != len(set(header)):
        raise ValueError("Column headers must be unique - this file has a duplicate header.")

    rows = []
    for row in reader:
        if len(rows) >= MAX_ROWS:
            break
        rows.append(row)

    if not rows:
        raise ValueError("The file has a header row but no data rows.")

    values_by_column = {name: [] for name in header}

    for row in rows:
        for index, name in enumerate(header):
            value = row[index].strip() if index < len(row) else ""
            values_by_column[name].append(value)

    row_count = len(rows)
    columns = []
    column_stats = {}
    column_samples = {}

    for name in header:

        raw_values = values_by_column[name]
        non_null_values = [v for v in raw_values if v != ""]

        data_type = _infer_data_type(non_null_values)
        is_nullable = "YES" if len(non_null_values) < len(raw_values) else "NO"

        columns.append((name, data_type, is_nullable))

        column_stats[name] = {
            "non_null": len(non_null_values),
            "distinct": len(set(non_null_values)),
        }

        column_samples[name] = non_null_values[:SAMPLE_SIZE]

    return {
        "datasets": [{
            "schema_name": schema_name,
            "table_name": table_name,
            "columns": columns,
            "row_count": row_count,
            "column_stats": column_stats,
            "column_samples": column_samples,
        }],
        "foreign_keys": [],
    }
