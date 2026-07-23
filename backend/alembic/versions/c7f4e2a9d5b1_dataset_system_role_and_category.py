"""dataset system_role and data_category

Revision ID: c7f4e2a9d5b1
Revises: b6e2a4c8f1d3
Create Date: 2026-07-23 18:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c7f4e2a9d5b1'
down_revision: Union[str, None] = 'b6e2a4c8f1d3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # system_role: NULL / "SYSTEM_OF_RECORD" / "SYSTEM_OF_REFERENCE".
    # A simple per-dataset tag - set by a steward, never inferred -
    # marking whether this dataset is the authoritative source for
    # its entity, or a derived/downstream copy of one.
    op.add_column(
        'datasets',
        sa.Column('system_role', sa.String(), nullable=True)
    )

    # data_category: NULL / "MASTER" / "REFERENCE" / "TRANSACTIONAL" /
    # "ANALYTICAL". Auto-classified once at creation time via a naming
    # heuristic (see app/utils/data_classification.py), overridable
    # afterward by a steward through the existing governance-update
    # endpoint.
    op.add_column(
        'datasets',
        sa.Column('data_category', sa.String(), nullable=True)
    )


def downgrade() -> None:
    op.drop_column('datasets', 'data_category')
    op.drop_column('datasets', 'system_role')
