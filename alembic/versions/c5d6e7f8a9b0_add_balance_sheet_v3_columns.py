"""Add balance sheet V3 columns (provisions LP, deferred tax, reserves)

Revision ID: c5d6e7f8a9b0
Revises: a1f2b3c4d5e6
Create Date: 2026-03-11

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c5d6e7f8a9b0'
down_revision = 'a1f2b3c4d5e6'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Passivo Não Circulante: 2 new fields
    op.add_column('org_initial_balances',
        sa.Column('provisions_long_term', sa.Numeric(15, 2), server_default='0', nullable=True))
    op.add_column('org_initial_balances',
        sa.Column('deferred_tax_liabilities', sa.Numeric(15, 2), server_default='0', nullable=True))

    # Patrimônio Líquido: 1 new field
    op.add_column('org_initial_balances',
        sa.Column('reserves_and_adjustments', sa.Numeric(15, 2), server_default='0', nullable=True))


def downgrade() -> None:
    op.drop_column('org_initial_balances', 'reserves_and_adjustments')
    op.drop_column('org_initial_balances', 'deferred_tax_liabilities')
    op.drop_column('org_initial_balances', 'provisions_long_term')
