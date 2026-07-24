"""risks and controls

Revision ID: f2a7c9e4b6d1
Revises: e8b3a5c1d7f4
Create Date: 2026-07-25 09:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f2a7c9e4b6d1'
down_revision: Union[str, None] = 'e8b3a5c1d7f4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'controls',
        sa.Column('id', sa.String(length=36), primary_key=True),
        sa.Column('organization_id', sa.String(length=36), sa.ForeignKey('organizations.id'), nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('control_type', sa.String(), nullable=False, server_default='PREVENTIVE'),
        sa.Column('status', sa.String(), nullable=False, server_default='NOT_TESTED'),
        sa.Column('owner_user_id', sa.String(length=36), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('last_tested_at', sa.DateTime(), nullable=True),
        sa.Column('created_by', sa.String(length=36), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
    )
    op.create_index('ix_controls_organization_id', 'controls', ['organization_id'])

    op.create_table(
        'risks',
        sa.Column('id', sa.String(length=36), primary_key=True),
        sa.Column('organization_id', sa.String(length=36), sa.ForeignKey('organizations.id'), nullable=False),
        sa.Column('title', sa.String(), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('category', sa.String(), nullable=False, server_default='OTHER'),
        sa.Column('likelihood', sa.String(), nullable=False, server_default='MEDIUM'),
        sa.Column('impact', sa.String(), nullable=False, server_default='MEDIUM'),
        sa.Column('status', sa.String(), nullable=False, server_default='OPEN'),
        sa.Column('owner_user_id', sa.String(length=36), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('created_by', sa.String(length=36), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
    )
    op.create_index('ix_risks_organization_id', 'risks', ['organization_id'])
    op.create_index('ix_risks_status', 'risks', ['status'])

    op.create_table(
        'risk_dataset_links',
        sa.Column('id', sa.String(length=36), primary_key=True),
        sa.Column('risk_id', sa.String(length=36), sa.ForeignKey('risks.id'), nullable=False),
        sa.Column('dataset_id', sa.String(length=36), sa.ForeignKey('datasets.id'), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.UniqueConstraint('risk_id', 'dataset_id', name='uq_risk_dataset_link'),
    )
    op.create_index('ix_risk_dataset_links_risk_id', 'risk_dataset_links', ['risk_id'])
    op.create_index('ix_risk_dataset_links_dataset_id', 'risk_dataset_links', ['dataset_id'])

    op.create_table(
        'risk_process_links',
        sa.Column('id', sa.String(length=36), primary_key=True),
        sa.Column('risk_id', sa.String(length=36), sa.ForeignKey('risks.id'), nullable=False),
        sa.Column('process_id', sa.String(length=36), sa.ForeignKey('business_processes.id'), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.UniqueConstraint('risk_id', 'process_id', name='uq_risk_process_link'),
    )
    op.create_index('ix_risk_process_links_risk_id', 'risk_process_links', ['risk_id'])
    op.create_index('ix_risk_process_links_process_id', 'risk_process_links', ['process_id'])

    op.create_table(
        'risk_control_links',
        sa.Column('id', sa.String(length=36), primary_key=True),
        sa.Column('risk_id', sa.String(length=36), sa.ForeignKey('risks.id'), nullable=False),
        sa.Column('control_id', sa.String(length=36), sa.ForeignKey('controls.id'), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.UniqueConstraint('risk_id', 'control_id', name='uq_risk_control_link'),
    )
    op.create_index('ix_risk_control_links_risk_id', 'risk_control_links', ['risk_id'])
    op.create_index('ix_risk_control_links_control_id', 'risk_control_links', ['control_id'])


def downgrade() -> None:
    op.drop_index('ix_risk_control_links_control_id', table_name='risk_control_links')
    op.drop_index('ix_risk_control_links_risk_id', table_name='risk_control_links')
    op.drop_table('risk_control_links')

    op.drop_index('ix_risk_process_links_process_id', table_name='risk_process_links')
    op.drop_index('ix_risk_process_links_risk_id', table_name='risk_process_links')
    op.drop_table('risk_process_links')

    op.drop_index('ix_risk_dataset_links_dataset_id', table_name='risk_dataset_links')
    op.drop_index('ix_risk_dataset_links_risk_id', table_name='risk_dataset_links')
    op.drop_table('risk_dataset_links')

    op.drop_index('ix_risks_status', table_name='risks')
    op.drop_index('ix_risks_organization_id', table_name='risks')
    op.drop_table('risks')

    op.drop_index('ix_controls_organization_id', table_name='controls')
    op.drop_table('controls')
