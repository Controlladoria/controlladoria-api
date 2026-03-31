"""add_terms_and_privacy_agreement

Revision ID: 2636badaee2d
Revises: f5c40baa6c55
Create Date: 2026-01-28 23:06:41.187432

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '2636badaee2d'
down_revision: Union[str, None] = 'f5c40baa6c55'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add LGPD and Terms agreement fields to users table
    with op.batch_alter_table('users', schema=None) as batch_op:
        # Track if user agreed to Terms of Service
        batch_op.add_column(sa.Column('agreed_to_terms', sa.Boolean(), nullable=False, server_default='0'))
        batch_op.add_column(sa.Column('agreed_to_terms_at', sa.DateTime(), nullable=True))

        # Track if user agreed to Privacy Policy (LGPD compliance)
        batch_op.add_column(sa.Column('agreed_to_privacy', sa.Boolean(), nullable=False, server_default='0'))
        batch_op.add_column(sa.Column('agreed_to_privacy_at', sa.DateTime(), nullable=True))


def downgrade() -> None:
    # Remove Terms and Privacy agreement fields
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_column('agreed_to_privacy_at')
        batch_op.drop_column('agreed_to_privacy')
        batch_op.drop_column('agreed_to_terms_at')
        batch_op.drop_column('agreed_to_terms')
