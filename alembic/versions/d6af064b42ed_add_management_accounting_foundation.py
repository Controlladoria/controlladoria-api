"""add_management_accounting_foundation

Revision ID: d6af064b42ed
Revises: c42e9957c528
Create Date: 2026-01-28 15:57:20.415023

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd6af064b42ed'
down_revision: Union[str, None] = 'c42e9957c528'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ========== 1. ADD HIERARCHICAL STRUCTURE TO CHART OF ACCOUNTS ==========

    # Add hierarchy columns to chart_of_accounts table
    with op.batch_alter_table('chart_of_accounts', schema=None) as batch_op:
        batch_op.add_column(sa.Column('parent_account_id', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('account_level', sa.Integer(), nullable=True, server_default='3'))
        batch_op.add_column(sa.Column('is_detail_account', sa.Boolean(), nullable=True, server_default='1'))
        batch_op.add_column(sa.Column('full_path', sa.String(length=500), nullable=True))

        # Add cost classification columns
        batch_op.add_column(sa.Column('cost_type', sa.String(length=50), nullable=True))  # "fixed", "variable", "semi_variable"
        batch_op.add_column(sa.Column('is_direct_cost', sa.Boolean(), nullable=True, server_default='0'))

        # Add foreign key for hierarchy
        batch_op.create_foreign_key('fk_parent_account', 'chart_of_accounts', ['parent_account_id'], ['id'])

        # Add indexes
        batch_op.create_index('ix_parent_account_id', ['parent_account_id'])
        batch_op.create_index('ix_account_level', ['account_level'])

    # ========== 2. CREATE ACCOUNT DIMENSIONS TABLE ==========

    op.create_table(
        'account_dimensions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('dimension_type', sa.String(length=50), nullable=False),  # "cost_center", "project", "product", "customer"
        sa.Column('dimension_code', sa.String(length=100), nullable=False),  # "CC-001", "PRJ-2026-001"
        sa.Column('dimension_name', sa.String(length=255), nullable=False),  # "Departamento RH", "Projeto X"
        sa.Column('parent_dimension_id', sa.Integer(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='1'),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.ForeignKeyConstraint(['parent_dimension_id'], ['account_dimensions.id'], name='fk_parent_dimension'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], name='fk_dimensions_user'),
        sa.PrimaryKeyConstraint('id')
    )

    with op.batch_alter_table('account_dimensions', schema=None) as batch_op:
        batch_op.create_index('ix_dimension_user_id', ['user_id'])
        batch_op.create_index('ix_dimension_type', ['dimension_type'])
        batch_op.create_index('ix_dimension_code', ['dimension_code'])

    # ========== 3. ADD DIMENSIONS TO JOURNAL ENTRY LINES ==========

    with op.batch_alter_table('journal_entry_lines', schema=None) as batch_op:
        batch_op.add_column(sa.Column('cost_center_id', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('project_id', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('product_id', sa.Integer(), nullable=True))

        # Add foreign keys
        batch_op.create_foreign_key('fk_cost_center', 'account_dimensions', ['cost_center_id'], ['id'])
        batch_op.create_foreign_key('fk_project', 'account_dimensions', ['project_id'], ['id'])
        batch_op.create_foreign_key('fk_product', 'account_dimensions', ['product_id'], ['id'])

        # Add indexes
        batch_op.create_index('ix_cost_center_id', ['cost_center_id'])
        batch_op.create_index('ix_project_id', ['project_id'])
        batch_op.create_index('ix_product_id', ['product_id'])


def downgrade() -> None:
    # ========== 3. REMOVE DIMENSIONS FROM JOURNAL ENTRY LINES ==========

    with op.batch_alter_table('journal_entry_lines', schema=None) as batch_op:
        batch_op.drop_index('ix_product_id')
        batch_op.drop_index('ix_project_id')
        batch_op.drop_index('ix_cost_center_id')
        batch_op.drop_constraint('fk_product', type_='foreignkey')
        batch_op.drop_constraint('fk_project', type_='foreignkey')
        batch_op.drop_constraint('fk_cost_center', type_='foreignkey')
        batch_op.drop_column('product_id')
        batch_op.drop_column('project_id')
        batch_op.drop_column('cost_center_id')

    # ========== 2. DROP ACCOUNT DIMENSIONS TABLE ==========

    with op.batch_alter_table('account_dimensions', schema=None) as batch_op:
        batch_op.drop_index('ix_dimension_code')
        batch_op.drop_index('ix_dimension_type')
        batch_op.drop_index('ix_dimension_user_id')

    op.drop_table('account_dimensions')

    # ========== 1. REMOVE HIERARCHICAL STRUCTURE FROM CHART OF ACCOUNTS ==========

    with op.batch_alter_table('chart_of_accounts', schema=None) as batch_op:
        batch_op.drop_index('ix_account_level')
        batch_op.drop_index('ix_parent_account_id')
        batch_op.drop_constraint('fk_parent_account', type_='foreignkey')
        batch_op.drop_column('is_direct_cost')
        batch_op.drop_column('cost_type')
        batch_op.drop_column('full_path')
        batch_op.drop_column('is_detail_account')
        batch_op.drop_column('account_level')
        batch_op.drop_column('parent_account_id')
