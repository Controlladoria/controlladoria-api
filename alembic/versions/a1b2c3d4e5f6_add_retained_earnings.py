"""add retained_earnings to org_initial_balances

Revision ID: a1b2c3d4e5f6
Revises: f7a8b9c0d1e2
Create Date: 2026-04-16

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: str = 'f7a8b9c0d1e2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'org_initial_balances',
        sa.Column('retained_earnings', sa.Numeric(15, 2), server_default='0', nullable=False)
    )


def downgrade() -> None:
    op.drop_column('org_initial_balances', 'retained_earnings')
