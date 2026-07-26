"""github oauth login

Revision ID: c9d3f6a1b8e5
Revises: a5f8e1c3d9b7
Create Date: 2026-07-26 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'c9d3f6a1b8e5'
down_revision: Union[str, None] = 'a5f8e1c3d9b7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # batch mode: SQLite can't ALTER COLUMN or add a UNIQUE constraint
    # in place the way Postgres can, so this rebuilds the table under
    # the hood on SQLite while emitting plain ALTER TABLE statements
    # on Postgres - same migration works against both backends this
    # project targets (SQLite in dev/tests, Postgres via docker-compose).
    with op.batch_alter_table('users') as batch_op:
        batch_op.alter_column(
            'password_hash',
            existing_type=sa.String(),
            nullable=True,
        )
        batch_op.add_column(
            sa.Column(
                'auth_provider',
                sa.String(),
                nullable=False,
                server_default='password',
            ),
        )
        batch_op.add_column(
            sa.Column('github_id', sa.String(), nullable=True),
        )
        batch_op.create_unique_constraint('uq_users_github_id', ['github_id'])


def downgrade() -> None:
    with op.batch_alter_table('users') as batch_op:
        batch_op.drop_constraint('uq_users_github_id', type_='unique')
        batch_op.drop_column('github_id')
        batch_op.drop_column('auth_provider')
        batch_op.alter_column(
            'password_hash',
            existing_type=sa.String(),
            nullable=False,
        )
