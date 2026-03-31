"""add_known_items_table

Revision ID: e6b2c4d5f6a7
Revises: d5a1b2c3e4f5
Create Date: 2026-03-01

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e6b2c4d5f6a7'
down_revision: Union[str, None] = 'd5a1b2c3e4f5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'known_items',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('alias', sa.String(length=255), nullable=True),
        sa.Column('category', sa.String(length=100), nullable=True),
        sa.Column('transaction_type', sa.String(length=20), nullable=True),
        sa.Column('times_appeared', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('first_seen_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('last_seen_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index('ix_known_items_user_name', 'known_items', ['user_id', 'name'], unique=True)


def downgrade() -> None:
    op.drop_index('ix_known_items_user_name', table_name='known_items')
    op.drop_table('known_items')
