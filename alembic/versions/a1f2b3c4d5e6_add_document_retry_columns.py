"""add_document_retry_columns

Revision ID: a1f2b3c4d5e6
Revises: b2c3d4e5f6a7
Create Date: 2026-03-10 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1f2b3c4d5e6'
down_revision: Union[str, None] = 'b2c3d4e5f6a7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Background retry support: nightly retry of failed documents
    op.add_column('documents', sa.Column('retry_count', sa.Integer(), nullable=False, server_default='0'))
    op.add_column('documents', sa.Column('max_retries_exhausted', sa.Boolean(), nullable=False, server_default='false'))
    op.add_column('documents', sa.Column('last_retry_at', sa.DateTime(), nullable=True))


def downgrade() -> None:
    op.drop_column('documents', 'last_retry_at')
    op.drop_column('documents', 'max_retries_exhausted')
    op.drop_column('documents', 'retry_count')
