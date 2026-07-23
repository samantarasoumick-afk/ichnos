"""
Turns Tableau workbooks (from tableau_connector.fetch_workbooks_with_
upstream_tables) into pseudo-Datasets and lineage edges.

A workbook isn't a table, but it *consumes* tables and produces a
report someone relies on downstream - exactly the shape lineage is
meant to capture. So each workbook becomes its own Dataset (schema =
its Tableau project name, so two workbooks named "Overview" in
different projects don't collide; zero columns, zero rows, since it
has no schema of its own to report) and its upstreamTables are matched
against already-cataloged Datasets the same way LineageDiscoveryService
matches foreign keys: by schema_name + name, scoped to the current
organization. A workbook reading from a table nobody has scanned yet
just doesn't get a lineage edge for that table - there's nothing to
point at.
"""

from sqlalchemy.orm import Session

from app.models.dataset import Dataset
from app.models.lineage import DatasetLineage
from app.models.source import DataSource
from app.models.user import User

from app.services.dataset_ingestion_service import ingest_dataset_info


def ingest_tableau_workbooks(
    db: Session,
    source: DataSource,
    workbooks: list[dict],
    current_user: User,
) -> dict:

    dataset_and_workbook_by_luid = {}

    for workbook in workbooks:

        table_name = workbook.get("name")

        if not table_name:
            continue

        schema_name = workbook.get("project_name") or "tableau"

        dataset_info = {
            "schema_name": schema_name,
            "table_name": table_name,
            "columns": [],
            "row_count": 0,
            "column_stats": {},
            "column_samples": {},
        }

        dataset = ingest_dataset_info(db, source, dataset_info, current_user)

        key = workbook.get("luid") or f"{schema_name}.{table_name}"
        dataset_and_workbook_by_luid[key] = (dataset, workbook)

    lineage_edges_created = 0

    for dataset, workbook in dataset_and_workbook_by_luid.values():

        for upstream_table in workbook.get("upstream_tables") or []:

            upstream = (
                db.query(Dataset)
                .filter(
                    Dataset.schema_name == upstream_table.get("schema"),
                    Dataset.name == upstream_table.get("name"),
                    Dataset.organization_id == current_user.organization_id,
                )
                .first()
            )

            if not upstream or upstream.id == dataset.id:
                continue

            existing = (
                db.query(DatasetLineage)
                .filter(
                    DatasetLineage.upstream_dataset_id == upstream.id,
                    DatasetLineage.downstream_dataset_id == dataset.id,
                )
                .first()
            )

            if existing:
                continue

            db.add(
                DatasetLineage(
                    upstream_dataset_id=upstream.id,
                    downstream_dataset_id=dataset.id,
                    transformation_type="TABLEAU_WORKBOOK",
                    documentation_source="AUTO",
                )
            )

            lineage_edges_created += 1

    db.commit()

    return {
        "workbooks_discovered": len(dataset_and_workbook_by_luid),
        "lineage_edges_created": lineage_edges_created,
    }
