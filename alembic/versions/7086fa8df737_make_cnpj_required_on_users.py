"""make_cnpj_required_on_users

Revision ID: 7086fa8df737
Revises: d771cc44ef8d
Create Date: 2026-01-27 16:51:41.001980

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7086fa8df737'
down_revision: Union[str, None] = 'd771cc44ef8d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Update any existing NULL values to a placeholder
    # This ensures the NOT NULL constraint won't fail
    op.execute("UPDATE users SET cnpj = '00.000.000/0000-00' WHERE cnpj IS NULL")
    op.execute("UPDATE users SET full_name = 'Usuário' WHERE full_name IS NULL")
    op.execute("UPDATE users SET company_name = 'Empresa' WHERE company_name IS NULL")

    # Make cnpj, full_name, and company_name required (NOT NULL)
    with op.batch_alter_table('users') as batch_op:
        batch_op.alter_column('cnpj', nullable=False, existing_type=sa.String(18))
        batch_op.alter_column('full_name', nullable=False, existing_type=sa.String(255))
        batch_op.alter_column('company_name', nullable=False, existing_type=sa.String(255))


def downgrade() -> None:
    # Make fields nullable again
    with op.batch_alter_table('users') as batch_op:
        batch_op.alter_column('cnpj', nullable=True, existing_type=sa.String(18))
        batch_op.alter_column('full_name', nullable=True, existing_type=sa.String(255))
        batch_op.alter_column('company_name', nullable=True, existing_type=sa.String(255))
