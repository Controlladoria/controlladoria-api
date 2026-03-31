"""add_audit_trail_and_department_tracking

Revision ID: 9e0505d659e1
Revises:
Create Date: 2026-01-27

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '9e0505d659e1'
down_revision = '9b0c9e5c1e05'
branch_labels = None
depends_on = None


def upgrade():
    # Create audit_logs table
    op.create_table(
        'audit_logs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('document_id', sa.Integer(), nullable=True),
        sa.Column('action', sa.String(50), nullable=False),  # create, update, delete
        sa.Column('entity_type', sa.String(50), nullable=False),  # document, transaction, etc
        sa.Column('entity_id', sa.Integer(), nullable=True),
        sa.Column('before_value', sa.Text(), nullable=True),  # JSON string
        sa.Column('after_value', sa.Text(), nullable=True),  # JSON string
        sa.Column('changes_summary', sa.String(500), nullable=True),  # Human-readable summary
        sa.Column('ip_address', sa.String(45), nullable=True),
        sa.Column('user_agent', sa.String(500), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['document_id'], ['documents.id'], ondelete='CASCADE'),
    )

    # Create indexes for audit logs
    op.create_index('idx_audit_user_id', 'audit_logs', ['user_id'])
    op.create_index('idx_audit_document_id', 'audit_logs', ['document_id'])
    op.create_index('idx_audit_created_at', 'audit_logs', ['created_at'])
    op.create_index('idx_audit_user_document', 'audit_logs', ['user_id', 'document_id'])
    op.create_index('idx_audit_action', 'audit_logs', ['action'])

    # Add department field to documents
    op.add_column('documents', sa.Column('department', sa.String(100), nullable=True))
    op.create_index('idx_documents_department', 'documents', ['department'])

    # Add category field to documents for quick filtering (denormalized from JSON)
    op.add_column('documents', sa.Column('category', sa.String(100), nullable=True))
    op.create_index('idx_documents_category', 'documents', ['category'])

    # Add performance indexes
    op.create_index('idx_documents_user_status_date', 'documents', ['user_id', 'status', 'upload_date'])
    op.create_index('idx_documents_user_department', 'documents', ['user_id', 'department'])


def downgrade():
    # Drop indexes
    op.drop_index('idx_documents_user_department', table_name='documents')
    op.drop_index('idx_documents_user_status_date', table_name='documents')
    op.drop_index('idx_documents_category', table_name='documents')
    op.drop_index('idx_documents_department', table_name='documents')

    # Drop columns
    op.drop_column('documents', 'category')
    op.drop_column('documents', 'department')

    # Drop audit log indexes
    op.drop_index('idx_audit_action', table_name='audit_logs')
    op.drop_index('idx_audit_user_document', table_name='audit_logs')
    op.drop_index('idx_audit_created_at', table_name='audit_logs')
    op.drop_index('idx_audit_document_id', table_name='audit_logs')
    op.drop_index('idx_audit_user_id', table_name='audit_logs')

    # Drop audit_logs table
    op.drop_table('audit_logs')
