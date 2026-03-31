"""add_file_hash_for_duplicate_detection

Revision ID: 52b467345776
Revises: 00e7914d78a0
Create Date: 2026-02-04 00:03:03.989851

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '52b467345776'
down_revision: Union[str, None] = '00e7914d78a0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add file_hash column for duplicate detection
    op.add_column('documents', sa.Column('file_hash', sa.String(64), nullable=True))
    op.create_index('ix_documents_file_hash', 'documents', ['file_hash'])


def downgrade() -> None:
    # Remove file_hash column and index
    op.drop_index('ix_documents_file_hash', 'documents')
    op.drop_column('documents', 'file_hash')
