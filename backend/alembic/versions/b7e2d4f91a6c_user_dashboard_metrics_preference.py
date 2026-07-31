"""user dashboard metrics preference

Revision ID: b7e2d4f91a6c
Revises: a3f9c1e6b8d4
Create Date: 2026-07-31 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b7e2d4f91a6c'
down_revision: Union[str, None] = 'a3f9c1e6b8d4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('users', sa.Column('dashboard_metrics', sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column('users', 'dashboard_metrics')
