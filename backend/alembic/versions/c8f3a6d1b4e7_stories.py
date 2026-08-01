"""stories (user-authored guided tours)

Revision ID: c8f3a6d1b4e7
Revises: b7e2d4f91a6c
Create Date: 2026-08-01 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c8f3a6d1b4e7'
down_revision: Union[str, None] = 'b7e2d4f91a6c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'stories',
        sa.Column('id', sa.String(length=36), primary_key=True),
        sa.Column('organization_id', sa.String(length=36), sa.ForeignKey('organizations.id'), nullable=False),
        sa.Column('title', sa.String(), nullable=False),
        sa.Column('problem', sa.Text(), nullable=True),
        sa.Column('solution_summary', sa.Text(), nullable=True),
        sa.Column('created_by_user_id', sa.String(length=36), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('created_by_email', sa.String(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
    )
    op.create_index('ix_stories_organization_id', 'stories', ['organization_id'])

    op.create_table(
        'story_steps',
        sa.Column('id', sa.String(length=36), primary_key=True),
        sa.Column('story_id', sa.String(length=36), sa.ForeignKey('stories.id'), nullable=False),
        sa.Column('order_index', sa.Integer(), nullable=False),
        sa.Column('title', sa.String(), nullable=False),
        sa.Column('narrative', sa.Text(), nullable=False),
        sa.Column('path', sa.String(), nullable=False),
        sa.Column('dataset_schema_name', sa.String(), nullable=True),
        sa.Column('dataset_table_name', sa.String(), nullable=True),
        sa.Column('tab', sa.String(), nullable=True),
        sa.Column('query_params', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
    )
    op.create_index('ix_story_steps_story_id', 'story_steps', ['story_id'])


def downgrade() -> None:
    op.drop_index('ix_story_steps_story_id', table_name='story_steps')
    op.drop_table('story_steps')

    op.drop_index('ix_stories_organization_id', table_name='stories')
    op.drop_table('stories')
