"""billing fields, platform admin flag, marketing events

Revision ID: a1c4e8f2b6d9
Revises: e6f3b9c2a7d5
Create Date: 2026-07-27 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1c4e8f2b6d9'
down_revision: Union[str, None] = 'e6f3b9c2a7d5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- Organization: plan/billing/suspend --------------------------
    # Every existing org backfills to plan="starter", plan_status=
    # "trialing", is_suspended=False via server_default - nobody's
    # access changes the moment this migration runs.
    op.add_column(
        'organizations',
        sa.Column('plan', sa.String(), nullable=False, server_default='starter'),
    )
    op.add_column(
        'organizations',
        sa.Column('billing_cycle', sa.String(), nullable=True),
    )
    op.add_column(
        'organizations',
        sa.Column('plan_status', sa.String(), nullable=False, server_default='trialing'),
    )
    op.add_column(
        'organizations',
        sa.Column('is_suspended', sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        'organizations',
        sa.Column('stripe_customer_id', sa.String(), nullable=True),
    )
    op.add_column(
        'organizations',
        sa.Column('stripe_subscription_id', sa.String(), nullable=True),
    )
    # Unique indexes rather than named unique constraints - SQLite
    # can't ALTER a constraint onto an existing table without the
    # batch/copy-and-move dance, but a plain CREATE UNIQUE INDEX
    # enforces the same thing and works identically on Postgres.
    op.create_index(
        'uq_organizations_stripe_customer_id', 'organizations', ['stripe_customer_id'], unique=True
    )
    op.create_index(
        'uq_organizations_stripe_subscription_id', 'organizations', ['stripe_subscription_id'], unique=True
    )

    # --- User: platform-admin flag ------------------------------------
    op.add_column(
        'users',
        sa.Column('is_platform_admin', sa.Boolean(), nullable=False, server_default=sa.false()),
    )

    # --- Marketing events: website visitor + signup funnel tracking --
    # Deliberately unauthenticated-writable (POST from the public
    # marketing site) - anon_id is a client-generated random id (not
    # a person), organization_id/user_id only get filled in once a
    # visit converts into a real signup. No IP address or other
    # directly-identifying field is stored - see app/api/marketing.py.
    op.create_table(
        'marketing_events',
        sa.Column('id', sa.String(length=36), primary_key=True),
        sa.Column('event_type', sa.String(), nullable=False),
        sa.Column('anon_id', sa.String(), nullable=False),
        sa.Column('path', sa.String(), nullable=True),
        sa.Column('referrer', sa.String(), nullable=True),
        sa.Column('utm_source', sa.String(), nullable=True),
        sa.Column('utm_medium', sa.String(), nullable=True),
        sa.Column('utm_campaign', sa.String(), nullable=True),
        sa.Column('organization_id', sa.String(length=36), sa.ForeignKey('organizations.id'), nullable=True),
        sa.Column('user_id', sa.String(length=36), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
    )
    op.create_index('ix_marketing_events_anon_id', 'marketing_events', ['anon_id'])
    op.create_index('ix_marketing_events_event_type', 'marketing_events', ['event_type'])
    op.create_index('ix_marketing_events_organization_id', 'marketing_events', ['organization_id'])


def downgrade() -> None:
    op.drop_index('ix_marketing_events_organization_id', table_name='marketing_events')
    op.drop_index('ix_marketing_events_event_type', table_name='marketing_events')
    op.drop_index('ix_marketing_events_anon_id', table_name='marketing_events')
    op.drop_table('marketing_events')

    op.drop_column('users', 'is_platform_admin')

    op.drop_index('uq_organizations_stripe_subscription_id', table_name='organizations')
    op.drop_index('uq_organizations_stripe_customer_id', table_name='organizations')
    op.drop_column('organizations', 'stripe_subscription_id')
    op.drop_column('organizations', 'stripe_customer_id')
    op.drop_column('organizations', 'is_suspended')
    op.drop_column('organizations', 'plan_status')
    op.drop_column('organizations', 'billing_cycle')
    op.drop_column('organizations', 'plan')
