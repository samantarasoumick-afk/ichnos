"""business process narrative field

Revision ID: e1c4a7b3f9d2
Revises: f2a7c9e4b6d1
Create Date: 2026-07-24 09:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e1c4a7b3f9d2'
down_revision: Union[str, None] = 'f2a7c9e4b6d1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Free-text description of how the datasets linked to this
    # process actually interact - e.g. "A Customer (Master) orders
    # (Transactional) from a Store (Master) in Mumbai (Reference)."
    # Deliberately plain text rather than a structured graph: the goal
    # is a human-readable story a steward writes once, not a new
    # lineage engine.
    op.add_column(
        'business_processes',
        sa.Column('narrative', sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('business_processes', 'narrative')
