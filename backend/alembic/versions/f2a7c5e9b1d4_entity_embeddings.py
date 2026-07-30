"""entity embeddings cache

Revision ID: f2a7c5e9b1d4
Revises: a1c4e8f2b6d9
Create Date: 2026-07-30 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f2a7c5e9b1d4'
down_revision: Union[str, None] = 'a1c4e8f2b6d9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'entity_embeddings',
        sa.Column('id', sa.String(length=36), primary_key=True),
        sa.Column('organization_id', sa.String(length=36), sa.ForeignKey('organizations.id'), nullable=False),
        sa.Column('entity_type', sa.String(), nullable=False),
        sa.Column('entity_id', sa.String(length=36), nullable=False),
        sa.Column('text_hash', sa.String(length=64), nullable=False),
        sa.Column('model', sa.String(), nullable=False),
        sa.Column('dimension', sa.Integer(), nullable=False),
        sa.Column('vector', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.UniqueConstraint('entity_type', 'entity_id', name='uq_entity_embedding_entity'),
    )
    op.create_index(
        'ix_entity_embeddings_organization_id',
        'entity_embeddings',
        ['organization_id'],
    )


def downgrade() -> None:
    op.drop_index('ix_entity_embeddings_organization_id', table_name='entity_embeddings')
    op.drop_table('entity_embeddings')
