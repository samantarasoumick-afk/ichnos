"""governance discussions

Revision ID: f1a3c5e7b9d2
Revises: e4f6b8d0a2c9
Create Date: 2026-07-23 09:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f1a3c5e7b9d2'
down_revision: Union[str, None] = 'e4f6b8d0a2c9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'governance_threads',
        sa.Column('id', sa.String(length=36), primary_key=True),
        sa.Column('organization_id', sa.String(length=36), sa.ForeignKey('organizations.id'), nullable=False),
        sa.Column('dataset_id', sa.String(length=36), sa.ForeignKey('datasets.id'), nullable=True),
        sa.Column('thread_type', sa.String(), nullable=False, server_default='QUESTION'),
        sa.Column('title', sa.String(), nullable=False),
        sa.Column('body', sa.String(), nullable=True),
        sa.Column('status', sa.String(), nullable=False, server_default='OPEN'),
        sa.Column('created_by', sa.String(length=36), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('resolved_by', sa.String(length=36), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('resolved_at', sa.DateTime(), nullable=True),
        sa.Column('resolution_note', sa.String(), nullable=True),
    )
    op.create_index(
        'ix_governance_threads_organization_id',
        'governance_threads',
        ['organization_id'],
    )
    op.create_index(
        'ix_governance_threads_dataset_id',
        'governance_threads',
        ['dataset_id'],
    )
    op.create_index(
        'ix_governance_threads_status',
        'governance_threads',
        ['status'],
    )

    op.create_table(
        'governance_thread_replies',
        sa.Column('id', sa.String(length=36), primary_key=True),
        sa.Column('thread_id', sa.String(length=36), sa.ForeignKey('governance_threads.id'), nullable=False),
        sa.Column('body', sa.String(), nullable=False),
        sa.Column('created_by', sa.String(length=36), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
    )
    op.create_index(
        'ix_governance_thread_replies_thread_id',
        'governance_thread_replies',
        ['thread_id'],
    )


def downgrade() -> None:
    op.drop_index('ix_governance_thread_replies_thread_id', table_name='governance_thread_replies')
    op.drop_table('governance_thread_replies')

    op.drop_index('ix_governance_threads_status', table_name='governance_threads')
    op.drop_index('ix_governance_threads_dataset_id', table_name='governance_threads')
    op.drop_index('ix_governance_threads_organization_id', table_name='governance_threads')
    op.drop_table('governance_threads')
