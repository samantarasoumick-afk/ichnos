"""column description and sample_values

Revision ID: d4a7c2e9f6b3
Revises: c7f4e2a9d5b1
Create Date: 2026-07-23 19:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd4a7c2e9f6b3'
down_revision: Union[str, None] = 'c7f4e2a9d5b1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Steward-authored context for a specific column - never
    # auto-set, unlike every other field on this table.
    op.add_column(
        'columns',
        sa.Column('description', sa.String(), nullable=True)
    )

    # JSON-encoded array of example values, refreshed on every
    # scan/upload - purely descriptive, so it refreshes even for
    # columns a steward has manually reclassified.
    op.add_column(
        'columns',
        sa.Column('sample_values', sa.String(), nullable=True)
    )


def downgrade() -> None:
    op.drop_column('columns', 'sample_values')
    op.drop_column('columns', 'description')
