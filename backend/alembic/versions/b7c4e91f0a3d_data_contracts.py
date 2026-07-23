"""data contracts

Revision ID: b7c4e91f0a3d
Revises: 9f2a5c7e1d3b
Create Date: 2026-07-22 15:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b7c4e91f0a3d'
down_revision: Union[str, None] = '9f2a5c7e1d3b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'data_contracts',
        sa.Column('id', sa.String(length=36), primary_key=True),
        sa.Column('dataset_id', sa.String(length=36), sa.ForeignKey('datasets.id'), nullable=False),
        sa.Column('version', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('status', sa.String(), nullable=False, server_default='DRAFT'),
        sa.Column('owner', sa.String(), nullable=True),
        sa.Column('schema_expectations', sa.JSON(), nullable=False),
        sa.Column('quality_thresholds', sa.JSON(), nullable=True),
        sa.Column('freshness_sla_hours', sa.Integer(), nullable=True),
        sa.Column('last_evaluated_at', sa.DateTime(), nullable=True),
        sa.Column('last_status', sa.String(), nullable=True),
        sa.Column('last_breach_details', sa.String(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
    )
    op.create_index(
        'ix_data_contracts_dataset_id',
        'data_contracts',
        ['dataset_id'],
    )


def downgrade() -> None:
    op.drop_index('ix_data_contracts_dataset_id', table_name='data_contracts')
    op.drop_table('data_contracts')
