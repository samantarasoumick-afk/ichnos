# Metadata Scanner

The metadata scanner is implemented in `backend/app/api/scanner.py` and `backend/app/connectors/postgres_scanner.py`.

## Current Support

PostgreSQL sources are supported through `scan_postgres_source`.

## Scan Responsibilities

The scan flow:

1. Loads the registered source.
2. Connects to PostgreSQL.
3. Discovers tables, columns, and foreign keys.
4. Creates or updates datasets.
5. Replaces scanned columns for existing datasets.
6. Classifies columns.
7. Generates descriptions and summaries.
8. Profiles data quality.
9. Discovers lineage from foreign keys.

## Future Work

- Scan history table.
- Connector interface for additional source types.
- Incremental scans.
- Scan failure records and retry handling.
