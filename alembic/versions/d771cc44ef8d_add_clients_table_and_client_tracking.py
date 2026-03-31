"""Add clients table and client tracking

Revision ID: d771cc44ef8d
Revises: 9e0505d659e1
Create Date: 2026-01-27 13:21:09.002712

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd771cc44ef8d'
down_revision: Union[str, None] = '9e0505d659e1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create clients table
    op.create_table('clients',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=255), nullable=False),
    sa.Column('legal_name', sa.String(length=255), nullable=True),
    sa.Column('tax_id', sa.String(length=20), nullable=True),
    sa.Column('email', sa.String(length=255), nullable=True),
    sa.Column('phone', sa.String(length=20), nullable=True),
    sa.Column('address', sa.Text(), nullable=True),
    sa.Column('client_type', sa.String(length=20), nullable=False),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.Column('notes', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_user_client_name', 'clients', ['user_id', 'name'], unique=False)
    op.create_index('idx_user_tax_id', 'clients', ['user_id', 'tax_id'], unique=False)
    op.create_index(op.f('ix_clients_client_type'), 'clients', ['client_type'], unique=False)
    op.create_index(op.f('ix_clients_id'), 'clients', ['id'], unique=False)
    op.create_index(op.f('ix_clients_name'), 'clients', ['name'], unique=False)
    op.create_index(op.f('ix_clients_tax_id'), 'clients', ['tax_id'], unique=False)
    op.create_index(op.f('ix_clients_user_id'), 'clients', ['user_id'], unique=False)

    # Add client_id to documents
    op.add_column('documents', sa.Column('client_id', sa.Integer(), nullable=True))
    op.create_index('idx_user_client', 'documents', ['user_id', 'client_id'], unique=False)
    op.create_index(op.f('ix_documents_client_id'), 'documents', ['client_id'], unique=False)


def downgrade() -> None:
    # Remove client_id from documents
    op.drop_index(op.f('ix_documents_client_id'), table_name='documents')
    op.drop_index('idx_user_client', table_name='documents')
    op.drop_column('documents', 'client_id')

    # Drop clients table and indexes
    op.drop_index(op.f('ix_clients_user_id'), table_name='clients')
    op.drop_index(op.f('ix_clients_tax_id'), table_name='clients')
    op.drop_index(op.f('ix_clients_name'), table_name='clients')
    op.drop_index(op.f('ix_clients_id'), table_name='clients')
    op.drop_index(op.f('ix_clients_client_type'), table_name='clients')
    op.drop_index('idx_user_tax_id', table_name='clients')
    op.drop_index('idx_user_client_name', table_name='clients')
    op.drop_table('clients')
