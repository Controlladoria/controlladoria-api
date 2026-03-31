"""add organization_id to documents

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-03-23

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'e5f6a7b8c9d0'
down_revision = 'd4e5f6a7b8c9'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add organization_id column to documents (nullable for existing docs)
    op.add_column('documents', sa.Column('organization_id', sa.Integer(), nullable=True))
    op.create_index('idx_documents_organization_id', 'documents', ['organization_id'])
    op.create_foreign_key(
        'fk_documents_organization_id',
        'documents', 'organizations',
        ['organization_id'], ['id'],
        ondelete='SET NULL',
    )

    # Backfill: assign existing documents to the user's active_org_id
    op.execute("""
        UPDATE documents
        SET organization_id = (
            SELECT u.active_org_id
            FROM users u
            WHERE u.id = documents.user_id
        )
        WHERE organization_id IS NULL
        AND user_id IS NOT NULL
    """)


def downgrade() -> None:
    op.drop_constraint('fk_documents_organization_id', 'documents', type_='foreignkey')
    op.drop_index('idx_documents_organization_id', table_name='documents')
    op.drop_column('documents', 'organization_id')
