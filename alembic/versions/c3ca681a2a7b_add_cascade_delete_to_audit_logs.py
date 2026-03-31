"""remove_foreign_key_from_audit_logs_document_id

Revision ID: c3ca681a2a7b
Revises: a55ee899db08
Create Date: 2026-02-03 21:33:04.196670

Removes foreign key constraint on audit_logs.document_id to preserve
audit history when documents are deleted. Document ID and name are
already stored in entity_id and changes_summary.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c3ca681a2a7b'
down_revision: Union[str, None] = 'a55ee899db08'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Drop foreign key constraint - keep document_id as regular integer
    op.drop_constraint('audit_logs_document_id_fkey', 'audit_logs', type_='foreignkey')


def downgrade() -> None:
    # Restore foreign key constraint
    op.create_foreign_key(
        'audit_logs_document_id_fkey',
        'audit_logs',
        'documents',
        ['document_id'],
        ['id']
    )
