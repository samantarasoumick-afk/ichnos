"""lineage transformation/filter documentation

Revision ID: e4f6b8d0a2c9
Revises: d9e1a3c5f7b2
Create Date: 2026-07-22 19:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e4f6b8d0a2c9'
down_revision: Union[str, None] = 'd9e1a3c5f7b2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'dataset_lineage',
        sa.Column('transformation_description', sa.Text(), nullable=True)
    )
    op.add_column(
        'dataset_lineage',
        sa.Column('filter_logic', sa.Text(), nullable=True)
    )
    op.add_column(
        'dataset_lineage',
        sa.Column(
            'documentation_source',
            sa.String(),
            nullable=False,
            server_default='AUTO'
        )
    )


def downgrade() -> None:
    op.drop_column('dataset_lineage', 'documentation_source')
    op.drop_column('dataset_lineage', 'filter_logic')
    op.drop_column('dataset_lineage', 'transformation_description')
