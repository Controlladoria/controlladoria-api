"""add_partner_feedback_schema_changes

Revision ID: b4e8f7c39a12
Revises: 97f0a90cd7b5
Create Date: 2026-02-20 00:00:00.000000

Adds all schema changes for 10 partner feedback items:
- Item 4: NFe cancellation support (is_cancellation, cancelled_by_document_id, cancels_document_id)
- Item 7: CNPJ warning instead of block (cnpj_mismatch, cnpj_warning_message)
- Item 8: Upload queue (queue_position, queued_at)
- Item 9: Validation flow (PENDING_VALIDATION status, document_validation_rows table)
- Item 4: CANCELLED status enum value
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b4e8f7c39a12'
down_revision: Union[str, None] = '97f0a90cd7b5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Detect dialect for enum handling
    bind = op.get_bind()
    dialect = bind.dialect.name

    # =========================================================================
    # 1. Add new enum values to DocumentStatus
    # =========================================================================
    if dialect == 'postgresql':
        # PostgreSQL: ALTER TYPE to add new enum values
        op.execute("ALTER TYPE documentstatus ADD VALUE IF NOT EXISTS 'PENDING_VALIDATION'")
        op.execute("ALTER TYPE documentstatus ADD VALUE IF NOT EXISTS 'CANCELLED'")
    # SQLite: enum is stored as VARCHAR, no type changes needed

    # =========================================================================
    # 2. Add columns to documents table (Items 4, 7, 8)
    # =========================================================================

    # Item 7: CNPJ warning instead of block
    op.add_column('documents', sa.Column(
        'cnpj_mismatch', sa.Boolean(), nullable=False, server_default='false'
    ))
    op.add_column('documents', sa.Column(
        'cnpj_warning_message', sa.Text(), nullable=True
    ))

    # Item 8: Upload queue
    op.add_column('documents', sa.Column(
        'queue_position', sa.Integer(), nullable=True
    ))
    op.add_column('documents', sa.Column(
        'queued_at', sa.DateTime(), nullable=True
    ))

    # Item 4: NFe cancellation support
    op.add_column('documents', sa.Column(
        'is_cancellation', sa.Boolean(), nullable=False, server_default='false'
    ))
    op.add_column('documents', sa.Column(
        'cancelled_by_document_id', sa.Integer(), sa.ForeignKey('documents.id'), nullable=True
    ))
    op.add_column('documents', sa.Column(
        'cancels_document_id', sa.Integer(), sa.ForeignKey('documents.id'), nullable=True
    ))

    # Note: department, category columns already added by migration 9e0505d659e1
    # Note: file_hash column already added by migration 52b467345776

    # =========================================================================
    # 3. Create document_validation_rows table (Item 9)
    # =========================================================================
    op.create_table(
        'document_validation_rows',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('document_id', sa.Integer(), nullable=False),
        sa.Column('row_index', sa.Integer(), nullable=False),
        sa.Column('description', sa.String(length=500), nullable=True),
        sa.Column('transaction_date', sa.String(length=20), nullable=True),
        sa.Column('amount', sa.Integer(), nullable=True),
        sa.Column('category', sa.String(length=100), nullable=True),
        sa.Column('transaction_type', sa.String(length=20), nullable=True),
        sa.Column('is_validated', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('validated_at', sa.DateTime(), nullable=True),
        sa.Column('original_data_json', sa.Text(), nullable=True),
        sa.Column('user_id', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['document_id'], ['documents.id']),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_document_validation_rows_id', 'document_validation_rows', ['id'])
    op.create_index('ix_document_validation_rows_document_id', 'document_validation_rows', ['document_id'])
    op.create_index('idx_validation_doc_row', 'document_validation_rows', ['document_id', 'row_index'])

    # Note: idx_user_client index already added by migration d771cc44ef8d


def downgrade() -> None:
    # Drop validation rows table
    op.drop_index('idx_validation_doc_row', table_name='document_validation_rows')
    op.drop_index('ix_document_validation_rows_document_id', table_name='document_validation_rows')
    op.drop_index('ix_document_validation_rows_id', table_name='document_validation_rows')
    op.drop_table('document_validation_rows')

    # Drop added columns from documents
    op.drop_column('documents', 'cancels_document_id')
    op.drop_column('documents', 'cancelled_by_document_id')
    op.drop_column('documents', 'is_cancellation')
    op.drop_column('documents', 'queued_at')
    op.drop_column('documents', 'queue_position')
    op.drop_column('documents', 'cnpj_warning_message')
    op.drop_column('documents', 'cnpj_mismatch')

    # Note: PostgreSQL enum values cannot be removed without recreating the type.
    # Downgrade leaves PENDING_VALIDATION and CANCELLED in the enum.
