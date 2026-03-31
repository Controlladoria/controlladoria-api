"""widen_regime_tributario_column

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-03-10 16:40:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b2c3d4e5f6a7'
down_revision: Union[str, None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # BrasilAPI can return regime_tributario values longer than 50 chars
    op.alter_column('users', 'regime_tributario',
                    existing_type=sa.String(50),
                    type_=sa.String(100),
                    existing_nullable=True)
    op.alter_column('organizations', 'regime_tributario',
                    existing_type=sa.String(50),
                    type_=sa.String(100),
                    existing_nullable=True)


def downgrade() -> None:
    op.alter_column('organizations', 'regime_tributario',
                    existing_type=sa.String(100),
                    type_=sa.String(50),
                    existing_nullable=True)
    op.alter_column('users', 'regime_tributario',
                    existing_type=sa.String(100),
                    type_=sa.String(50),
                    existing_nullable=True)
