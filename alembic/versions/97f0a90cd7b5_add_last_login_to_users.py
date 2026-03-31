"""add_last_login_to_users

Revision ID: 97f0a90cd7b5
Revises: 52b467345776
Create Date: 2026-02-05 23:39:32.644630

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '97f0a90cd7b5'
down_revision: Union[str, None] = '52b467345776'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add last_login column to users table
    op.add_column('users', sa.Column('last_login', sa.DateTime(), nullable=True))
    op.create_index('ix_users_last_login', 'users', ['last_login'], unique=False)


def downgrade() -> None:
    # Remove last_login column from users table
    op.drop_index('ix_users_last_login', table_name='users')
    op.drop_column('users', 'last_login')
