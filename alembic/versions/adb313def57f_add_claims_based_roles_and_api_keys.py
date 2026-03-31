"""add_claims_based_roles_and_api_keys

Revision ID: adb313def57f
Revises: 2636badaee2d
Create Date: 2026-01-28 23:57:20.043711

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'adb313def57f'
down_revision: Union[str, None] = '2636badaee2d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Remove management accounting features and clean up indexes"""

    # === Remove management accounting features ===
    # IMPORTANT: Drop foreign key constraints BEFORE dropping the referenced table
    op.drop_index('ix_cost_center_id', table_name='journal_entry_lines')
    op.drop_index('ix_product_id', table_name='journal_entry_lines')
    op.drop_index('ix_project_id', table_name='journal_entry_lines')
    op.drop_constraint('fk_cost_center', 'journal_entry_lines', type_='foreignkey')
    op.drop_constraint('fk_project', 'journal_entry_lines', type_='foreignkey')
    op.drop_constraint('fk_product', 'journal_entry_lines', type_='foreignkey')
    op.drop_column('journal_entry_lines', 'cost_center_id')
    op.drop_column('journal_entry_lines', 'project_id')
    op.drop_column('journal_entry_lines', 'product_id')

    # Now safe to drop account_dimensions table
    op.drop_index('ix_dimension_code', table_name='account_dimensions')
    op.drop_index('ix_dimension_type', table_name='account_dimensions')
    op.drop_index('ix_dimension_user_id', table_name='account_dimensions')
    op.drop_table('account_dimensions')

    # Drop management accounting columns from chart_of_accounts
    op.drop_index('ix_account_level', table_name='chart_of_accounts')
    op.drop_index('ix_parent_account_id', table_name='chart_of_accounts')
    op.drop_constraint('fk_parent_account', 'chart_of_accounts', type_='foreignkey')
    op.drop_column('chart_of_accounts', 'account_level')
    op.drop_column('chart_of_accounts', 'is_detail_account')
    op.drop_column('chart_of_accounts', 'full_path')
    op.drop_column('chart_of_accounts', 'cost_type')
    op.drop_column('chart_of_accounts', 'is_direct_cost')
    op.drop_column('chart_of_accounts', 'parent_account_id')

    # === Update audit_logs foreign keys (remove CASCADE) ===
    op.drop_constraint('audit_logs_user_id_fkey', 'audit_logs', type_='foreignkey')
    op.drop_constraint('audit_logs_document_id_fkey', 'audit_logs', type_='foreignkey')
    op.create_foreign_key(None, 'audit_logs', 'documents', ['document_id'], ['id'])
    op.create_foreign_key(None, 'audit_logs', 'users', ['user_id'], ['id'])

    # === Clean up indexes ===
    # Drop composite index on clients (will be replaced by individual indexes)
    op.drop_index('ix_clients_user_type', table_name='clients')

    # Add foreign key for client_id in documents (column already exists from d771cc44ef8d)
    op.create_foreign_key(None, 'documents', 'clients', ['client_id'], ['id'])

    # Remove old subscription index
    op.drop_index('ix_subscriptions_status_period_end', table_name='subscriptions')

    # === Update team_invitations indexes ===
    op.drop_constraint('uq_invitation_token', 'team_invitations', type_='unique')
    op.drop_index('ix_team_invitations_token', table_name='team_invitations')
    op.create_index(op.f('ix_team_invitations_token'), 'team_invitations', ['token'], unique=True)
    op.create_index(op.f('ix_team_invitations_id'), 'team_invitations', ['id'], unique=False)

    # === Update users CNPJ to unique index ===
    op.alter_column('users', 'cnpj',
               existing_type=sa.VARCHAR(length=18),
               type_=sa.String(length=50),
               existing_nullable=False)
    op.drop_constraint('uq_users_cnpj', 'users', type_='unique')
    op.drop_index('ix_users_cnpj', table_name='users')
    op.create_index(op.f('ix_users_cnpj'), 'users', ['cnpj'], unique=True)


def downgrade() -> None:
    """Restore management accounting features"""

    # IMPORTANT: Create account_dimensions table BEFORE adding foreign keys that reference it
    op.create_table('account_dimensions',
    sa.Column('id', sa.INTEGER(), nullable=False),
    sa.Column('user_id', sa.INTEGER(), nullable=False),
    sa.Column('dimension_type', sa.VARCHAR(length=50), nullable=False),
    sa.Column('dimension_code', sa.VARCHAR(length=100), nullable=False),
    sa.Column('dimension_name', sa.VARCHAR(length=255), nullable=False),
    sa.Column('parent_dimension_id', sa.INTEGER(), nullable=True),
    sa.Column('is_active', sa.BOOLEAN(), server_default=sa.text("'1'"), nullable=False),
    sa.Column('created_at', sa.DATETIME(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.ForeignKeyConstraint(['parent_dimension_id'], ['account_dimensions.id'], name='fk_parent_dimension'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name='fk_dimensions_user'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_dimension_user_id', 'account_dimensions', ['user_id'], unique=False)
    op.create_index('ix_dimension_type', 'account_dimensions', ['dimension_type'], unique=False)
    op.create_index('ix_dimension_code', 'account_dimensions', ['dimension_code'], unique=False)

    # Restore users CNPJ indexes
    op.drop_index(op.f('ix_users_cnpj'), table_name='users')
    op.create_index('ix_users_cnpj', 'users', ['cnpj'], unique=False)
    op.create_unique_constraint('uq_users_cnpj', 'users', ['cnpj'])
    op.alter_column('users', 'cnpj',
               existing_type=sa.String(length=50),
               type_=sa.VARCHAR(length=18),
               existing_nullable=False)

    # Restore team_invitations indexes
    op.drop_index(op.f('ix_team_invitations_id'), table_name='team_invitations')
    op.drop_index(op.f('ix_team_invitations_token'), table_name='team_invitations')
    op.create_index('ix_team_invitations_token', 'team_invitations', ['token'], unique=False)
    op.create_unique_constraint('uq_invitation_token', 'team_invitations', ['token'])

    # Restore subscription index
    op.create_index('ix_subscriptions_status_period_end', 'subscriptions', ['status', 'current_period_end'], unique=False)

    # Remove client_id foreign key from documents
    op.drop_constraint(None, 'documents', type_='foreignkey')

    # Restore clients index
    op.create_index('ix_clients_user_type', 'clients', ['user_id', 'client_type'], unique=False)

    # Restore chart_of_accounts management accounting columns
    op.add_column('chart_of_accounts', sa.Column('parent_account_id', sa.INTEGER(), nullable=True))
    op.add_column('chart_of_accounts', sa.Column('is_direct_cost', sa.BOOLEAN(), server_default=sa.text("'0'"), nullable=True))
    op.add_column('chart_of_accounts', sa.Column('cost_type', sa.VARCHAR(length=50), nullable=True))
    op.add_column('chart_of_accounts', sa.Column('full_path', sa.VARCHAR(length=500), nullable=True))
    op.add_column('chart_of_accounts', sa.Column('is_detail_account', sa.BOOLEAN(), server_default=sa.text("'1'"), nullable=True))
    op.add_column('chart_of_accounts', sa.Column('account_level', sa.INTEGER(), server_default=sa.text("'3'"), nullable=True))
    op.create_foreign_key('fk_parent_account', 'chart_of_accounts', 'chart_of_accounts', ['parent_account_id'], ['id'])
    op.create_index('ix_parent_account_id', 'chart_of_accounts', ['parent_account_id'], unique=False)
    op.create_index('ix_account_level', 'chart_of_accounts', ['account_level'], unique=False)

    # Restore audit_logs CASCADE foreign keys
    op.drop_constraint('audit_logs_user_id_fkey', 'audit_logs', type_='foreignkey')
    op.drop_constraint('audit_logs_document_id_fkey', 'audit_logs', type_='foreignkey')
    op.create_foreign_key(None, 'audit_logs', 'documents', ['document_id'], ['id'], ondelete='CASCADE')
    op.create_foreign_key(None, 'audit_logs', 'users', ['user_id'], ['id'], ondelete='CASCADE')

    # Now safe to add foreign keys that reference account_dimensions
    op.add_column('journal_entry_lines', sa.Column('product_id', sa.INTEGER(), nullable=True))
    op.add_column('journal_entry_lines', sa.Column('project_id', sa.INTEGER(), nullable=True))
    op.add_column('journal_entry_lines', sa.Column('cost_center_id', sa.INTEGER(), nullable=True))
    op.create_foreign_key('fk_product', 'journal_entry_lines', 'account_dimensions', ['product_id'], ['id'])
    op.create_foreign_key('fk_project', 'journal_entry_lines', 'account_dimensions', ['project_id'], ['id'])
    op.create_foreign_key('fk_cost_center', 'journal_entry_lines', 'account_dimensions', ['cost_center_id'], ['id'])
    op.create_index('ix_project_id', 'journal_entry_lines', ['project_id'], unique=False)
    op.create_index('ix_product_id', 'journal_entry_lines', ['product_id'], unique=False)
    op.create_index('ix_cost_center_id', 'journal_entry_lines', ['cost_center_id'], unique=False)
