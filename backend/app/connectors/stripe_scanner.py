"""
Stripe scanner - same dataset_info contract every other connector
produces (see postgres_scanner.py for the canonical shape), but for a
SaaS-of-record billing API rather than a database. There's no schema
to introspect, so this samples one page of real records per Stripe
object type and infers a schema from them, the same approach
s3_scanner.py uses for schemaless object storage.

connection_config keys:
  - api_key (required): a Stripe secret key (sk_test_... or
    sk_live_...) with at least read access to the objects below.
    Stripe's REST API authenticates via HTTP Basic Auth with the key
    as the username and no password.

Covers the objects a small/mid-size company's billing stack actually
revolves around - who are our customers, what did they pay, are they
subscribed - rather than trying to mirror all of Stripe's ~50 API
resources. Each becomes one catalog dataset under a fixed "stripe"
schema namespace (Stripe isn't multi-schema like a database).

Only one page (up to PAGE_LIMIT records) is fetched per object type -
a metadata scan samples the shape of the data to build a catalog
entry, it doesn't mirror an entire Stripe account. row_count reflects
only what was sampled, the same lower-bound convention s3_scanner.py
uses for a truncated read.
"""

import json

import requests


STRIPE_API_BASE = "https://api.stripe.com/v1"

REQUEST_TIMEOUT_SECONDS = 30

SAMPLE_SIZE = 20

PAGE_LIMIT = 100

STRIPE_OBJECTS = ["customers", "charges", "invoices", "subscriptions"]


class StripeConnectionError(Exception):
    """
    Raised for anything that keeps us from getting a usable object
    list back: an unreachable API, a rejected/revoked key, or a
    malformed response. Registered in
    app/connectors/registry.py's CONNECTION_ERRORS so the scanner
    endpoint turns this into a clean 502 rather than a raw 500 - a bad
    or revoked API key is a user mistake, not a server bug.
    """


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


def _flatten_value(value):
    """
    Stripe objects nest freely (address, metadata, line items,
    payment_method_details...). Column-level type inference here only
    reasons about scalar fields - anything nested is kept as its JSON
    string form rather than silently dropped, so it's still visible in
    a sample value even though it isn't typed as its own scalar
    column.
    """

    if value is None or isinstance(value, (str, int, float, bool)):
        return value

    return json.dumps(value)


def _fetch_object_page(api_key: str, object_name: str) -> list:

    url = f"{STRIPE_API_BASE}/{object_name}"

    try:
        response = requests.get(
            url,
            auth=(api_key, ""),
            params={"limit": PAGE_LIMIT},
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
    except requests.RequestException as exc:
        raise StripeConnectionError(
            f"Unable to reach Stripe API at {url}: {exc}"
        )

    if response.status_code == 401:
        raise StripeConnectionError(
            "Stripe rejected this API key (401 Unauthorized) - check "
            "that it's correct and hasn't been revoked."
        )

    if response.status_code != 200:
        raise StripeConnectionError(
            f"Stripe API request to '{object_name}' failed "
            f"({response.status_code}): {response.text[:300]}"
        )

    try:
        payload = response.json()
    except ValueError as exc:
        raise StripeConnectionError(
            f"Unexpected response from Stripe for '{object_name}': {exc}"
        )

    return payload.get("data") or []


def _dataset_from_records(object_name: str, records: list):

    if not records:
        return None

    # Column set = union of top-level keys seen across the sample -
    # Stripe objects of the same type are usually uniform, but this
    # avoids dropping a field that happens to be null/missing on the
    # very first record.
    ordered_keys = []
    seen = set()

    for record in records:
        for key in record.keys():
            if key not in seen:
                seen.add(key)
                ordered_keys.append(key)

    columns = []
    column_stats = {}
    column_samples = {}

    for key in ordered_keys:

        raw_values = [record.get(key) for record in records]
        flattened = [_flatten_value(v) for v in raw_values]
        non_null_values = [v for v in flattened if v is not None]

        data_type = _infer_data_type(non_null_values)
        is_nullable = "YES" if len(non_null_values) < len(flattened) else "NO"

        columns.append((key, data_type, is_nullable))

        column_stats[key] = {
            "non_null": len(non_null_values),
            "distinct": len(set(str(v) for v in non_null_values)),
        }

        column_samples[key] = [str(v) for v in non_null_values[:SAMPLE_SIZE]]

    return {
        "schema_name": "stripe",
        "table_name": object_name,
        "columns": columns,
        "row_count": len(records),
        "column_stats": column_stats,
        "column_samples": column_samples,
    }


def scan_stripe_source(config: dict):

    api_key = (config or {}).get("api_key")

    if not api_key:
        raise StripeConnectionError(
            "A Stripe API key (connection_config.api_key) is required."
        )

    datasets = []

    for object_name in STRIPE_OBJECTS:

        records = _fetch_object_page(api_key, object_name)
        dataset_info = _dataset_from_records(object_name, records)

        if dataset_info:
            datasets.append(dataset_info)

    return {
        "datasets": datasets,
        # Stripe's object relationships (e.g. Charge.customer ->
        # Customer.id) are real foreign keys conceptually, but they
        # don't come back in the DB-style tuple shape
        # LineageDiscoveryService expects from information_schema.
        # Auto-discovering them is a reasonable follow-up, not
        # attempted here - document the edge manually via the lineage
        # feature in the meantime.
        "foreign_keys": [],
    }
