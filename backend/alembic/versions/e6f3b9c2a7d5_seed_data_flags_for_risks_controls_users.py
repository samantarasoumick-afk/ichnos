"""seed data flags for risks, controls, users

Revision ID: e6f3b9c2a7d5
Revises: d4e7a2c9f6b3
Create Date: 2026-07-27 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e6f3b9c2a7d5'
down_revision: Union[str, None] = 'd4e7a2c9f6b3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Same is_seed_data marker already used on data_sources/
    # business_glossary_terms/business_processes, extended to risks,
    # controls, and users so the demo seeder can populate the risk
    # register, control library, and team roster too, while
    # clear_demo_data() can still precisely undo only what it added.
    op.add_column(
        'risks',
        sa.Column('is_seed_data', sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        'controls',
        sa.Column('is_seed_data', sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        'users',
        sa.Column('is_seed_data', sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_column('users', 'is_seed_data')
    op.drop_column('controls', 'is_seed_data')
    op.drop_column('risks', 'is_seed_data')
