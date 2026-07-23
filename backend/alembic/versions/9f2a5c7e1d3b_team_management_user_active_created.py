"""team management: user is_active + created_at

Revision ID: 9f2a5c7e1d3b
Revises: 18e3f127bef9
Create Date: 2026-07-22 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '9f2a5c7e1d3b'
down_revision: Union[str, None] = '18e3f127bef9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'users',
        sa.Column(
            'is_active',
            sa.Boolean(),
            nullable=False,
            server_default=sa.true()
        )
    )
    op.add_column(
        'users',
        sa.Column('created_at', sa.DateTime(), nullable=True)
    )


def downgrade() -> None:
    op.drop_column('users', 'created_at')
    op.drop_column('users', 'is_active')
