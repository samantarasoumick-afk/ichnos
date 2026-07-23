"""
Data quality profiling from real scan data - no randomness.

Every score is derived from numbers `postgres_scanner.scan_postgres_source`
already collected during the scan (row counts, per-column non-null/distinct
counts, and a small sample of actual values), so profiling a dataset costs
zero extra queries against the source database.
"""

from app.utils.privacy_engine import (
    EMAIL_REGEX,
    PHONE_REGEX,
    AADHAAR_REGEX,
    PAN_REGEX,
    IFSC_REGEX,
    PASSPORT_REGEX,
    CREDIT_CARD_REGEX,
)


_NUMERIC_TYPES = {
    "integer", "bigint", "smallint", "numeric",
    "real", "double precision", "decimal",
}

# Reuse the exact same patterns the privacy engine uses for
# classification, so "validity" means "does this column's data match
# the pattern its name implies" consistently across both systems.
_NAME_PATTERNS = [
    (["email"], EMAIL_REGEX),
    (["phone", "mobile"], PHONE_REGEX),
    (["aadhaar", "aadhar"], AADHAAR_REGEX),
    (["pan_number", "pan_no", "pancard"], PAN_REGEX),
    (["ifsc"], IFSC_REGEX),
    (["passport"], PASSPORT_REGEX),
    (["credit_card", "card_number", "debit_card"], CREDIT_CARD_REGEX),
]


def _expected_pattern_for(column_name: str):

    name = (column_name or "").lower()

    for keywords, pattern in _NAME_PATTERNS:
        if any(keyword in name for keyword in keywords):
            return pattern

    return None


def _is_numeric_parseable(value) -> bool:

    try:
        float(value)
        return True
    except (TypeError, ValueError):
        return False


def _avg_pct(ratios: list, default: float) -> float:

    if not ratios:
        return default

    return round((sum(ratios) / len(ratios)) * 100, 2)


class DataQualityService:

    @staticmethod
    def profile(dataset_info: dict) -> dict:
        """
        `dataset_info` is one entry from scan_postgres_source's
        "datasets" list: {"columns": [(name, type, nullable), ...],
        "row_count": int, "column_stats": {...}, "column_samples": {...}}.

        - completeness: avg(non-null / total rows) across columns
        - uniqueness: avg(distinct / non-null) across columns
        - validity: for columns whose name implies a checkable
          pattern (email, phone, Aadhaar, PAN, ...), the fraction of
          sampled values that actually match it. Columns with no
          checkable pattern don't count against validity.
        - consistency: for numeric-typed columns, the fraction of
          sampled values that actually parse as numbers. Non-numeric
          columns don't count against consistency.
        - freshness: 100 - this profile is generated at scan time, so
          the data is maximally fresh by definition. Ongoing staleness
          between scans is tracked live via Dataset.freshness_status,
          not duplicated here.
        """

        columns = dataset_info.get("columns") or []
        row_count = dataset_info.get("row_count") or 0
        column_stats = dataset_info.get("column_stats") or {}
        column_samples = dataset_info.get("column_samples") or {}

        if not columns or row_count == 0:

            return {
                "completeness": 0.0,
                "uniqueness": 0.0,
                "validity": 0.0,
                "consistency": 0.0,
                "freshness": 100.0,
                "overall_score": 0.0,
            }

        completeness_ratios = []
        uniqueness_ratios = []
        validity_ratios = []
        consistency_ratios = []

        for column_name, data_type, _nullable in columns:

            stats = column_stats.get(column_name) or {}
            non_null = stats.get("non_null")
            distinct = stats.get("distinct")

            if non_null is not None:

                completeness_ratios.append(non_null / row_count)

                if non_null > 0 and distinct is not None:
                    uniqueness_ratios.append(distinct / non_null)

            samples = [
                v for v in column_samples.get(column_name, [])
                if v not in (None, "")
            ]

            expected_pattern = _expected_pattern_for(column_name)

            if expected_pattern is not None and samples:
                matches = sum(
                    1 for v in samples
                    if expected_pattern.match(str(v).strip())
                )
                validity_ratios.append(matches / len(samples))

            if (data_type or "").lower() in _NUMERIC_TYPES and samples:
                parseable = sum(
                    1 for v in samples
                    if _is_numeric_parseable(v)
                )
                consistency_ratios.append(parseable / len(samples))

        completeness = _avg_pct(completeness_ratios, 100.0)
        uniqueness = _avg_pct(uniqueness_ratios, 100.0)
        validity = _avg_pct(validity_ratios, 100.0)
        consistency = _avg_pct(consistency_ratios, 100.0)
        freshness = 100.0

        overall = round(
            (completeness + uniqueness + validity + consistency + freshness) / 5,
            2,
        )

        return {
            "completeness": completeness,
            "uniqueness": uniqueness,
            "validity": validity,
            "consistency": consistency,
            "freshness": freshness,
            "overall_score": overall,
        }
