from sqlalchemy.orm import Session

from app.models.dataset import Dataset
from app.models.lineage import DatasetLineage


class LineageDiscoveryService:

    @staticmethod
    def discover(
        db: Session,
        source_id: str,
        foreign_keys: list,
        organization_id: str,
    ):
        """
        organization_id scopes both dataset lookups below - without
        it, two tenants that happen to both have a "public.customers"
        table (an extremely common name) could get a lineage edge
        silently attached to the wrong tenant's dataset, since the
        lookup is by schema/table name alone.
        """

        created = 0

        for fk in foreign_keys:

            (
                schema,
                table,
                column,
                foreign_schema,
                foreign_table,
                foreign_column,
            ) = fk

            upstream = (
                db.query(Dataset)
                .filter(
                    Dataset.schema_name == foreign_schema,
                    Dataset.name == foreign_table,
                    Dataset.organization_id == organization_id,
                )
                .first()
            )

            downstream = (
                db.query(Dataset)
                .filter(
                    Dataset.schema_name == schema,
                    Dataset.name == table,
                    Dataset.organization_id == organization_id,
                )
                .first()
            )

            if not upstream or not downstream:
                continue

            exists = (
                db.query(DatasetLineage)
                .filter(
                    DatasetLineage.upstream_dataset_id == upstream.id,
                    DatasetLineage.downstream_dataset_id == downstream.id,
                )
                .first()
            )

            if exists:
                continue

            db.add(
                DatasetLineage(
                    upstream_dataset_id=upstream.id,
                    downstream_dataset_id=downstream.id,
                    transformation_type="FOREIGN_KEY",
                    documentation_source="AUTO",
                )
            )

            created += 1

        db.commit()

        return created