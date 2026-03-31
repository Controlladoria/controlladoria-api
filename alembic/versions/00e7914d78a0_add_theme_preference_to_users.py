"""add_theme_preference_to_users

Revision ID: 00e7914d78a0
Revises: c3ca681a2a7b
Create Date: 2026-02-03 22:10:39.378308

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '00e7914d78a0'
down_revision: Union[str, None] = 'c3ca681a2a7b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add theme_preference column to users table
    # Possible values: 'light', 'dark', 'system'
    op.add_column('users', sa.Column('theme_preference', sa.String(length=20), nullable=False, server_default='system'))


def downgrade() -> None:
    # Remove theme_preference column from users table
    op.drop_column('users', 'theme_preference')
