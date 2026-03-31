"""add email_verification_token_created_at

Revision ID: d6674609c7b3
Revises: f7a8b9c0d1e2
Create Date: 2026-03-02 12:28:00.433310

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd6674609c7b3'
down_revision: Union[str, None] = 'f7a8b9c0d1e2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('users', sa.Column('email_verification_token_created_at', sa.DateTime(), nullable=True))


def downgrade() -> None:
    op.drop_column('users', 'email_verification_token_created_at')
