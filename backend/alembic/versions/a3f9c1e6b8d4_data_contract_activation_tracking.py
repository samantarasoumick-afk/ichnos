"""data contract activation tracking

Revision ID: a3f9c1e6b8d4
Revises: c4d8f1a6e3b9
Create Date: 2026-07-30 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a3f9c1e6b8d4'
down_revision: Union[str, None] = 'c4d8f1a6e3b9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('data_contracts', sa.Column('activated_by_email', sa.String(), nullable=True))
    op.add_column('data_contracts', sa.Column('activated_at', sa.DateTime(), nullable=True))


def downgrade() -> None:
    op.drop_column('data_contracts', 'activated_at')
    op.drop_column('data_contracts', 'activated_by_email')
