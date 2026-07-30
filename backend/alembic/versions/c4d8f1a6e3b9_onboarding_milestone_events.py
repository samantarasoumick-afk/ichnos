"""onboarding milestone events

Revision ID: c4d8f1a6e3b9
Revises: f2a7c5e9b1d4
Create Date: 2026-07-30 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c4d8f1a6e3b9'
down_revision: Union[str, None] = 'f2a7c5e9b1d4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'onboarding_milestone_events',
        sa.Column('id', sa.String(length=36), primary_key=True),
        sa.Column('organization_id', sa.String(length=36), sa.ForeignKey('organizations.id'), nullable=False),
        sa.Column('user_id', sa.String(length=36), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('milestone_key', sa.String(), nullable=False),
        sa.Column('achieved_at', sa.DateTime(), nullable=False),
        sa.UniqueConstraint('user_id', 'milestone_key', name='uq_onboarding_milestone_user_key'),
    )
    op.create_index(
        'ix_onboarding_milestone_events_organization_id',
        'onboarding_milestone_events',
        ['organization_id'],
    )
    op.create_index(
        'ix_onboarding_milestone_events_user_id',
        'onboarding_milestone_events',
        ['user_id'],
    )


def downgrade() -> None:
    op.drop_index('ix_onboarding_milestone_events_user_id', table_name='onboarding_milestone_events')
    op.drop_index('ix_onboarding_milestone_events_organization_id', table_name='onboarding_milestone_events')
    op.drop_table('onboarding_milestone_events')
