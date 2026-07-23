"""governance thread issue type + raised_for stakeholder

Revision ID: e8b3a5c1d7f4
Revises: d4a7c2e9f6b3
Create Date: 2026-07-23 20:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e8b3a5c1d7f4'
down_revision: Union[str, None] = 'd4a7c2e9f6b3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Who this ISSUE thread is being raised for, so it can be followed
    # up on with a specific stakeholder rather than just left open for
    # anyone to notice. Optional and only meaningful for thread_type
    # ISSUE, but not DB-constrained to that - a QUESTION/PROPOSAL could
    # reasonably carry it too if someone wants to flag a person on it.
    # No inline ForeignKey here - SQLite can't ALTER TABLE ADD
    # CONSTRAINT without batch mode, and every other single-column
    # addition in this migration history (system_role, data_category,
    # description, sample_values) follows the same plain-column
    # pattern. The FK relationship still exists at the ORM level in
    # app/models/governance_thread.py for joins/queries.
    op.add_column(
        'governance_threads',
        sa.Column('raised_for_user_id', sa.String(length=36), nullable=True)
    )
    op.create_index(
        'ix_governance_threads_raised_for_user_id',
        'governance_threads',
        ['raised_for_user_id'],
    )


def downgrade() -> None:
    op.drop_index('ix_governance_threads_raised_for_user_id', table_name='governance_threads')
    op.drop_column('governance_threads', 'raised_for_user_id')
