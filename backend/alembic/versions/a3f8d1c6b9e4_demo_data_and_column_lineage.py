"""demo data flag + column-level lineage

Revision ID: a3f8d1c6b9e4
Revises: f1a3c5e7b9d2
Create Date: 2026-07-23 14:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a3f8d1c6b9e4'
down_revision: Union[str, None] = 'f1a3c5e7b9d2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'data_sources',
        sa.Column(
            'is_seed_data',
            sa.Boolean(),
            nullable=False,
            server_default=sa.false()
        )
    )

    op.create_table(
        'column_lineage',
        sa.Column('id', sa.String(length=36), primary_key=True),
        sa.Column('upstream_dataset_id', sa.String(length=36), sa.ForeignKey('datasets.id'), nullable=False),
        sa.Column('upstream_column_name', sa.String(), nullable=False),
        sa.Column('downstream_dataset_id', sa.String(length=36), sa.ForeignKey('datasets.id'), nullable=False),
        sa.Column('downstream_column_name', sa.String(), nullable=False),
        sa.Column('transformation_type', sa.String(), nullable=True),
        sa.Column('transformation_description', sa.Text(), nullable=True),
        sa.Column('documentation_source', sa.String(), nullable=False, server_default='AUTO'),
    )
    op.create_index(
        'ix_column_lineage_upstream_dataset_id',
        'column_lineage',
        ['upstream_dataset_id'],
    )
    op.create_index(
        'ix_column_lineage_downstream_dataset_id',
        'column_lineage',
        ['downstream_dataset_id'],
    )


def downgrade() -> None:
    op.drop_index('ix_column_lineage_downstream_dataset_id', table_name='column_lineage')
    op.drop_index('ix_column_lineage_upstream_dataset_id', table_name='column_lineage')
    op.drop_table('column_lineage')

    op.drop_column('data_sources', 'is_seed_data')
