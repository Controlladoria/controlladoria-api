"""add retained_earnings to org_initial_balances

Revision ID: f8a9b0c1d2e3
Revises: e5f6a7b8c9d0
Create Date: 2026-04-16

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'f8a9b0c1d2e3'
down_revision: str = 'e5f6a7b8c9d0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'org_initial_balances',
        sa.Column('retained_earnings', sa.Numeric(15, 2), server_default='0', nullable=False)
    )


def downgrade() -> None:
    op.drop_column('org_initial_balances', 'retained_earnings')
