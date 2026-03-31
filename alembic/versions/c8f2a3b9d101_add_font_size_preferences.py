"""add_font_size_preferences

Revision ID: c8f2a3b9d101
Revises: b4e8f7c39a12
Create Date: 2026-03-01

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c8f2a3b9d101'
down_revision: Union[str, None] = 'b4e8f7c39a12'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add font_size_mobile and font_size_desktop columns to users table
    # Separate preferences per device type so mobile/desktop can have different sizes
    op.add_column('users', sa.Column('font_size_mobile', sa.String(length=10), nullable=False, server_default='medium'))
    op.add_column('users', sa.Column('font_size_desktop', sa.String(length=10), nullable=False, server_default='medium'))


def downgrade() -> None:
    op.drop_column('users', 'font_size_desktop')
    op.drop_column('users', 'font_size_mobile')
