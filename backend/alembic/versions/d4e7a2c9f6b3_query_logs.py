"""query logs

Revision ID: d4e7a2c9f6b3
Revises: c9d3f6a1b8e5
Create Date: 2026-07-26 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd4e7a2c9f6b3'
down_revision: Union[str, None] = 'c9d3f6a1b8e5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'query_logs',
        sa.Column('id', sa.String(length=36), primary_key=True),
        sa.Column('organization_id', sa.String(length=36), sa.ForeignKey('organizations.id'), nullable=False),
        sa.Column('actor_user_id', sa.String(length=36), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('actor_email', sa.String(), nullable=True),
        sa.Column('source', sa.String(), nullable=False),
        sa.Column('query_text', sa.Text(), nullable=False),
        sa.Column('matched', sa.Boolean(), nullable=False),
        sa.Column('result_count', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
    )
    op.create_index(
        'ix_query_logs_org_created',
        'query_logs',
        ['organization_id', 'created_at'],
    )
    op.create_index(
        'ix_query_logs_org_matched',
        'query_logs',
        ['organization_id', 'matched'],
    )


def downgrade() -> None:
    op.drop_index('ix_query_logs_org_matched', table_name='query_logs')
    op.drop_index('ix_query_logs_org_created', table_name='query_logs')
    op.drop_table('query_logs')
