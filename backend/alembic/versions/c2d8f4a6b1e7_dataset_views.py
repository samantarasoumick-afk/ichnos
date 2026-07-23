"""dataset views

Revision ID: c2d8f4a6b1e7
Revises: b7c4e91f0a3d
Create Date: 2026-07-22 17:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c2d8f4a6b1e7'
down_revision: Union[str, None] = 'b7c4e91f0a3d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'dataset_views',
        sa.Column('id', sa.String(length=36), primary_key=True),
        sa.Column('dataset_id', sa.String(length=36), sa.ForeignKey('datasets.id'), nullable=False),
        sa.Column('user_id', sa.String(length=36), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('viewed_at', sa.DateTime(), nullable=False),
    )
    op.create_index(
        'ix_dataset_views_dataset_id',
        'dataset_views',
        ['dataset_id'],
    )
    op.create_index(
        'ix_dataset_views_dataset_user',
        'dataset_views',
        ['dataset_id', 'user_id'],
    )


def downgrade() -> None:
    op.drop_index('ix_dataset_views_dataset_user', table_name='dataset_views')
    op.drop_index('ix_dataset_views_dataset_id', table_name='dataset_views')
    op.drop_table('dataset_views')
