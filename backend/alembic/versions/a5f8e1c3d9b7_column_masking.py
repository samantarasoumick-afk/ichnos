"""column masking

Revision ID: a5f8e1c3d9b7
Revises: b3d6f9a2c5e8
Create Date: 2026-07-26 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'a5f8e1c3d9b7'
down_revision: Union[str, None] = 'b3d6f9a2c5e8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'columns',
        sa.Column(
            'masked',
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )


def downgrade() -> None:
    op.drop_column('columns', 'masked')
