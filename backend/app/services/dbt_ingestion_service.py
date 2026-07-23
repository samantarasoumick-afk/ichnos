"""
Ingests a dbt project from its compiled artifacts (manifest.json,
optionally catalog.json) rather than a live connection - dbt itself
has no "scan me" API, but its manifest already contains everything a
live scanner would otherwise have to reverse-engineer: model
schema/table names, declared columns, and - critically - the exact
model-to-model dependency graph (depends_on) plus the compiled SQL
that produced each model. That graph is *richer* than what
LineageDiscoveryService derives from foreign keys, so this writes
DatasetLineage edges directly from it rather than routing through the
generic FK-tuple pipeline (which has no way to express "model A reads
from model B", only "column A.x references column B.y").

manifest.json alone (no catalog.json) still works: models get
ingested with their declared column names but "unknown" types, since
column *types* only exist in catalog.json (populated by `dbt docs
generate`, which actually queries the warehouse). Passing catalog={}
is the "manifest-only" case.
"""

from sqlalchemy.orm import Session

from app.models.lineage import DatasetLineage
from app.models.source import DataSource
from app.models.user import User

from app.services.dataset_ingestion_service import ingest_dataset_info


# dbt resource types that represent an actual materialized/queryable
# relation. Deliberately excludes "test" (not a dataset), "analysis"
# (not materialized), and "source" (not defined in `nodes` at all -
# dbt lists sources in a separate manifest key; wiring lineage to
# already-cataloged upstream sources is a natural follow-up but out of
# scope for this first pass, which only connects dbt models/seeds to
# each other).
INGESTIBLE_RESOURCE_TYPES = {"model", "seed", "snapshot"}

# Compiled SQL can be large; this is a display-length cap for the
# lineage edge's transformation_description, not a correctness limit.
MAX_TRANSFORMATION_DESCRIPTION_LENGTH = 4000


def _build_columns(node: dict, catalog_node: dict | None) -> list[tuple]:
    """
    Prefers catalog.json's columns (has real warehouse-introspected
    types, keyed by column name with an "index" for ordering) over
    manifest.json's (declared/documented only, no type information).
    """

    if catalog_node and catalog_node.get("columns"):

        items = sorted(
            catalog_node["columns"].values(),
            key=lambda c: c.get("index", 0),
        )

        return [
            (c["name"], c.get("type") or "unknown", "YES")
            for c in items
            if c.get("name")
        ]

    manifest_columns = node.get("columns") or {}

    return [
        (column_name, "unknown", "YES")
        for column_name in manifest_columns.keys()
    ]


def _extract_row_count(catalog_node: dict | None) -> int:
    """
    dbt only populates table stats (including row_count) when the
    adapter surfaces them at `dbt docs generate` time - not every
    adapter does, so this is best-effort and defaults to 0 (unknown)
    rather than guessing.
    """

    if not catalog_node:
        return 0

    row_stat = (catalog_node.get("stats") or {}).get("row_count") or {}
    value = row_stat.get("value")

    if isinstance(value, (int, float)):
        return int(value)

    return 0


def ingest_dbt_project(
    db: Session,
    source: DataSource,
    manifest: dict,
    catalog: dict,
    current_user: User,
) -> dict:

    manifest_nodes = manifest.get("nodes") or {}
    catalog_nodes = catalog.get("nodes") or {}

    dataset_by_unique_id = {}

    for unique_id, node in manifest_nodes.items():

        if node.get("resource_type") not in INGESTIBLE_RESOURCE_TYPES:
            continue

        table_name = node.get("alias") or node.get("name")

        if not table_name:
            continue

        schema_name = node.get("schema") or "dbt"

        catalog_node = catalog_nodes.get(unique_id)

        dataset_info = {
            "schema_name": schema_name,
            "table_name": table_name,
            "columns": _build_columns(node, catalog_node),
            "row_count": _extract_row_count(catalog_node),
            "column_stats": {},
            "column_samples": {},
        }

        dataset = ingest_dataset_info(db, source, dataset_info, current_user)

        # A dbt model's own documented description (written by
        # whoever built it) is more trustworthy than the generic
        # auto-generated one ingest_dataset_info() falls back to for
        # brand-new datasets.
        node_description = (node.get("description") or "").strip()

        if node_description and dataset.description != node_description:
            dataset.description = node_description
            db.commit()

        dataset_by_unique_id[unique_id] = dataset

    lineage_edges_created = 0

    for unique_id, node in manifest_nodes.items():

        downstream = dataset_by_unique_id.get(unique_id)

        if not downstream:
            continue

        depends_on = (node.get("depends_on") or {}).get("nodes") or []
        compiled_sql = node.get("compiled_code") or node.get("compiled_sql") or ""

        if compiled_sql:
            compiled_sql = compiled_sql.strip()[:MAX_TRANSFORMATION_DESCRIPTION_LENGTH]

        for upstream_unique_id in depends_on:

            upstream = dataset_by_unique_id.get(upstream_unique_id)

            if not upstream or upstream.id == downstream.id:
                continue

            existing = (
                db.query(DatasetLineage)
                .filter(
                    DatasetLineage.upstream_dataset_id == upstream.id,
                    DatasetLineage.downstream_dataset_id == downstream.id,
                )
                .first()
            )

            if existing:
                continue

            db.add(
                DatasetLineage(
                    upstream_dataset_id=upstream.id,
                    downstream_dataset_id=downstream.id,
                    transformation_type="dbt_model",
                    transformation_description=compiled_sql or None,
                    documentation_source="AUTO",
                )
            )

            lineage_edges_created += 1

    db.commit()

    return {
        "datasets_discovered": len(dataset_by_unique_id),
        "lineage_edges_created": lineage_edges_created,
    }
