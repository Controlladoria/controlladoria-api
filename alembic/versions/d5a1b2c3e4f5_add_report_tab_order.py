"""add_report_tab_order

Revision ID: d5a1b2c3e4f5
Revises: c8f2a3b9d101
Create Date: 2026-03-01

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd5a1b2c3e4f5'
down_revision: Union[str, None] = 'c8f2a3b9d101'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('users', sa.Column('report_tab_order', sa.String(length=50), nullable=False, server_default='dre,balanco,fluxo'))


def downgrade() -> None:
    op.drop_column('users', 'report_tab_order')
