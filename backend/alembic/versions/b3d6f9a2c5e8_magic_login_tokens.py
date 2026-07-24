"""magic login tokens (passwordless login)

Revision ID: b3d6f9a2c5e8
Revises: e1c4a7b3f9d2
Create Date: 2026-07-24 11:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b3d6f9a2c5e8'
down_revision: Union[str, None] = 'e1c4a7b3f9d2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'magic_login_tokens',
        sa.Column('id', sa.String(length=36), primary_key=True),
        sa.Column('user_id', sa.String(length=36), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('token_hash', sa.String(), nullable=False, unique=True),
        sa.Column('expires_at', sa.DateTime(), nullable=False),
        sa.Column('used_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
    )
    op.create_index('ix_magic_login_tokens_token_hash', 'magic_login_tokens', ['token_hash'], unique=True)
    op.create_index('ix_magic_login_tokens_user_id', 'magic_login_tokens', ['user_id'])


def downgrade() -> None:
    op.drop_index('ix_magic_login_tokens_user_id', table_name='magic_login_tokens')
    op.drop_index('ix_magic_login_tokens_token_hash', table_name='magic_login_tokens')
    op.drop_table('magic_login_tokens')
