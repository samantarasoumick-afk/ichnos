"""
Amazon S3 scanner - same dataset_info contract every other connector
produces (see postgres_scanner.py for the canonical shape), but for
an object-storage source rather than a live SQL database. There's no
schema to query, so this infers one by sampling a bounded prefix of
one representative object per "dataset" (a group of files under a
common folder) - CSV or newline-delimited JSON, the two shapes a data
lake export most commonly lands in.

connection_config keys:
  - bucket (required)
  - prefix (optional): only objects under this key prefix are scanned
  - region (optional)
  - access_key_id, secret_access_key (optional): if omitted, boto3
    falls back to its default credential chain (environment
    variables, shared config file, or an attached IAM role) - the
    same behavior any other AWS SDK use on this machine would have.

Unlike a SQL scanner, row counts and column stats here are read from
only the first SAMPLE_BYTES of one sample file per dataset, not the
whole object - downloading every partition file in full to get an
exact count isn't something a metadata scan should do. row_count is
exact only when the sampled object was small enough to be read in
full; otherwise it reports the sample size actually read, which is a
lower bound rather than a claim of completeness.
"""

import csv
import io
import json

import boto3

from botocore.exceptions import BotoCoreError, ClientError


SAMPLE_SIZE = 20

# How much of one representative object to download for schema
# sniffing and sampling - enough for a generous sample without
# pulling an entire multi-GB export into memory.
SAMPLE_BYTES = 512 * 1024

SUPPORTED_EXTENSIONS = (".csv", ".json", ".jsonl", ".ndjson")


def _looks_like_int(value) -> bool:
    if isinstance(value, bool):
        return False
    if isinstance(value, int):
        return True
    if not isinstance(value, str):
        return False
    try:
        int(value)
        return True
    except ValueError:
        return False


def _looks_like_float(value) -> bool:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return True
    if not isinstance(value, str):
        return False
    try:
        float(value)
        return True
    except ValueError:
        return False


def _infer_data_type(values: list) -> str:

    non_null = [v for v in values if v is not None and v != ""]

    if not non_null:
        return "varchar"

    if all(isinstance(v, bool) for v in non_null):
        return "boolean"

    if all(_looks_like_int(v) for v in non_null):
        return "integer"

    if all(_looks_like_float(v) for v in non_null):
        return "numeric"

    return "varchar"


def _dataset_name_for_key(key: str, prefix: str, bucket: str) -> str:
    """
    Groups objects under a common "table" the way a data lake export
    typically lands: files nested one level under the scan prefix
    (e.g. orders/part-0001.csv, orders/part-0002.csv) become one
    dataset named after that folder. Files sitting flat directly under
    the prefix (no further nesting) are grouped into a single dataset
    named after the prefix itself, since they're most likely
    partitions of the same export rather than unrelated tables.
    """

    relative = key[len(prefix):] if prefix and key.startswith(prefix) else key
    relative = relative.lstrip("/")

    if "/" in relative:
        return relative.split("/", 1)[0]

    trimmed_prefix = prefix.rstrip("/")

    if trimmed_prefix:
        return trimmed_prefix.split("/")[-1]

    return bucket


def _parse_csv_sample(text: str, truncated: bool):

    reader = csv.reader(io.StringIO(text))

    try:
        header = next(reader)
    except StopIteration:
        return None

    header = [name.strip() for name in header if name.strip()]

    if not header:
        return None

    rows = list(reader)

    # If the download was truncated mid-file, the last line read is
    # very likely a partial row - drop it rather than let a cut-off
    # value skew type inference or samples.
    if truncated and rows:
        rows = rows[:-1]

    values_by_column = {name: [] for name in header}

    for row in rows:
        for index, name in enumerate(header):
            value = row[index].strip() if index < len(row) else None
            values_by_column[name].append(value)

    return header, rows, values_by_column


def _parse_ndjson_sample(text: str, truncated: bool):

    lines = text.splitlines()

    if truncated and lines:
        lines = lines[:-1]

    records = []

    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(record, dict):
            records.append(record)

    if not records:
        return None

    header = list(records[0].keys())

    values_by_column = {name: [] for name in header}

    for record in records:
        for name in header:
            values_by_column[name].append(record.get(name))

    return header, records, values_by_column


def _build_dataset_from_sample(schema_name: str, table_name: str, key: str, obj_bytes: bytes, truncated: bool):

    try:
        text = obj_bytes.decode("utf-8-sig", errors="ignore")
    except Exception:
        return None

    if key.lower().endswith(".csv"):
        parsed = _parse_csv_sample(text, truncated)
    else:
        parsed = _parse_ndjson_sample(text, truncated)

    if not parsed:
        return None

    header, rows, values_by_column = parsed

    columns = []
    column_stats = {}
    column_samples = {}

    for name in header:

        raw_values = values_by_column[name]
        non_null_values = [v for v in raw_values if v is not None and v != ""]

        data_type = _infer_data_type(non_null_values)
        is_nullable = "YES" if len(non_null_values) < len(raw_values) else "NO"

        columns.append((name, data_type, is_nullable))

        column_stats[name] = {
            "non_null": len(non_null_values),
            "distinct": len(set(str(v) for v in non_null_values)),
        }

        column_samples[name] = [str(v) for v in non_null_values[:SAMPLE_SIZE]]

    return {
        "schema_name": schema_name,
        "table_name": table_name,
        "columns": columns,
        # Only an exact count if the whole object was read (not
        # truncated by SAMPLE_BYTES) - otherwise this is just the
        # sample size, not a claim about the full object.
        "row_count": len(rows) if not truncated else 0,
        "column_stats": column_stats,
        "column_samples": column_samples,
    }


def scan_s3_source(config: dict):

    bucket = config["bucket"]
    prefix = config.get("prefix") or ""

    client_kwargs = {}

    if config.get("region"):
        client_kwargs["region_name"] = config["region"]

    if config.get("access_key_id") and config.get("secret_access_key"):
        client_kwargs["aws_access_key_id"] = config["access_key_id"]
        client_kwargs["aws_secret_access_key"] = config["secret_access_key"]

    client = boto3.client("s3", **client_kwargs)

    try:
        paginator = client.get_paginator("list_objects_v2")
        pages = paginator.paginate(Bucket=bucket, Prefix=prefix)

        objects = []

        for page in pages:
            for obj in page.get("Contents", []):
                key = obj["Key"]
                if key.endswith("/"):
                    continue
                if not key.lower().endswith(SUPPORTED_EXTENSIONS):
                    continue
                objects.append(obj)

    except (ClientError, BotoCoreError) as exc:
        # Let the underlying botocore exception type/message through
        # unchanged rather than repackaging it - unlike a raw SQL
        # driver error, ClientError's message (e.g. "NoSuchBucket",
        # "AccessDenied") is already specific enough to act on.
        raise

    groups: dict[str, list] = {}

    for obj in objects:
        dataset_name = _dataset_name_for_key(obj["Key"], prefix, bucket)
        groups.setdefault(dataset_name, []).append(obj)

    datasets = []

    for dataset_name, group_objects in groups.items():

        # Sort so scans are deterministic across runs rather than
        # depending on S3's listing order for which file gets sampled.
        sample_obj = sorted(group_objects, key=lambda o: o["Key"])[0]
        key = sample_obj["Key"]
        size = sample_obj.get("Size", 0)
        truncated = size > SAMPLE_BYTES

        try:
            byte_range = f"bytes=0-{SAMPLE_BYTES - 1}" if truncated else None
            get_kwargs = {"Bucket": bucket, "Key": key}
            if byte_range:
                get_kwargs["Range"] = byte_range

            response = client.get_object(**get_kwargs)
            obj_bytes = response["Body"].read()

        except ClientError:
            continue

        dataset_info = _build_dataset_from_sample(
            schema_name=bucket,
            table_name=dataset_name,
            key=key,
            obj_bytes=obj_bytes,
            truncated=truncated,
        )

        if dataset_info:
            datasets.append(dataset_info)

    return {
        "datasets": datasets,
        # Object storage has no foreign-key concept - lineage between
        # S3 datasets and anything else has to be documented manually
        # (see the lineage documentation feature) rather than
        # auto-discovered.
        "foreign_keys": [],
    }
