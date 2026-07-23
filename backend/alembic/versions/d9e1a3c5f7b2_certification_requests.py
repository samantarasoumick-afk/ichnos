"""certification requests

Revision ID: d9e1a3c5f7b2
Revises: c2d8f4a6b1e7
Create Date: 2026-07-22 18:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd9e1a3c5f7b2'
down_revision: Union[str, None] = 'c2d8f4a6b1e7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'certification_requests',
        sa.Column('id', sa.String(length=36), primary_key=True),
        sa.Column('dataset_id', sa.String(length=36), sa.ForeignKey('datasets.id'), nullable=False),
        sa.Column('requested_by', sa.String(length=36), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('request_note', sa.String(), nullable=True),
        sa.Column('status', sa.String(), nullable=False, server_default='PENDING'),
        sa.Column('reviewed_by', sa.String(length=36), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('review_note', sa.String(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('reviewed_at', sa.DateTime(), nullable=True),
    )
    op.create_index(
        'ix_certification_requests_dataset_id',
        'certification_requests',
        ['dataset_id'],
    )
    op.create_index(
        'ix_certification_requests_status',
        'certification_requests',
        ['status'],
    )


def downgrade() -> None:
    op.drop_index('ix_certification_requests_status', table_name='certification_requests')
    op.drop_index('ix_certification_requests_dataset_id', table_name='certification_requests')
    op.drop_table('certification_requests')
