"""glossary term links + business processes

Revision ID: b6e2a4c8f1d3
Revises: a3f8d1c6b9e4
Create Date: 2026-07-23 16:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b6e2a4c8f1d3'
down_revision: Union[str, None] = 'a3f8d1c6b9e4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'business_glossary_terms',
        sa.Column('is_seed_data', sa.Boolean(), nullable=False, server_default=sa.false())
    )

    op.create_table(
        'glossary_term_links',
        sa.Column('id', sa.String(length=36), primary_key=True),
        sa.Column('term_id', sa.String(length=36), sa.ForeignKey('business_glossary_terms.id'), nullable=False),
        sa.Column('dataset_id', sa.String(length=36), sa.ForeignKey('datasets.id'), nullable=False),
        sa.Column('column_id', sa.String(length=36), sa.ForeignKey('columns.id'), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.UniqueConstraint('term_id', 'dataset_id', 'column_id', name='uq_glossary_link_term_dataset_column'),
    )
    op.create_index('ix_glossary_term_links_term_id', 'glossary_term_links', ['term_id'])
    op.create_index('ix_glossary_term_links_dataset_id', 'glossary_term_links', ['dataset_id'])

    op.create_table(
        'business_processes',
        sa.Column('id', sa.String(length=36), primary_key=True),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('owner', sa.String(), nullable=True),
        sa.Column('organization_id', sa.String(length=36), sa.ForeignKey('organizations.id'), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.Column('is_seed_data', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.UniqueConstraint('organization_id', 'name', name='uq_business_process_name_per_org'),
    )
    op.create_index('ix_business_processes_organization_id', 'business_processes', ['organization_id'])

    op.create_table(
        'business_process_links',
        sa.Column('id', sa.String(length=36), primary_key=True),
        sa.Column('process_id', sa.String(length=36), sa.ForeignKey('business_processes.id'), nullable=False),
        sa.Column('dataset_id', sa.String(length=36), sa.ForeignKey('datasets.id'), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.UniqueConstraint('process_id', 'dataset_id', name='uq_business_process_link_process_dataset'),
    )
    op.create_index('ix_business_process_links_process_id', 'business_process_links', ['process_id'])
    op.create_index('ix_business_process_links_dataset_id', 'business_process_links', ['dataset_id'])


def downgrade() -> None:
    op.drop_index('ix_business_process_links_dataset_id', table_name='business_process_links')
    op.drop_index('ix_business_process_links_process_id', table_name='business_process_links')
    op.drop_table('business_process_links')

    op.drop_index('ix_business_processes_organization_id', table_name='business_processes')
    op.drop_table('business_processes')

    op.drop_index('ix_glossary_term_links_dataset_id', table_name='glossary_term_links')
    op.drop_index('ix_glossary_term_links_term_id', table_name='glossary_term_links')
    op.drop_table('glossary_term_links')

    op.drop_column('business_glossary_terms', 'is_seed_data')
