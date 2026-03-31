"""add_unique_constraint_to_cnpj

Revision ID: 71677f4f3cfd
Revises: 7086fa8df737
Create Date: 2026-01-27 17:27:25.933176

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '71677f4f3cfd'
down_revision: Union[str, None] = '7086fa8df737'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # First, temporarily increase CNPJ column size to allow fixing duplicates
    connection = op.get_bind()

    # Increase column size temporarily (use batch_alter_table for SQLite compatibility)
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.alter_column('cnpj',
                              type_=sa.String(50),
                              existing_type=sa.String(18),
                              existing_nullable=False)

    # Find duplicate CNPJs
    result = connection.execute(sa.text("""
        SELECT cnpj, COUNT(*) as count
        FROM users
        GROUP BY cnpj
        HAVING COUNT(*) > 1
    """))

    duplicates = result.fetchall()

    # For each duplicate CNPJ, append user ID to duplicates (except the first occurrence)
    for cnpj, count in duplicates:
        # Get all user IDs with this CNPJ, ordered by creation date (oldest first)
        users = connection.execute(sa.text("""
            SELECT id FROM users WHERE cnpj = :cnpj ORDER BY created_at, id
        """), {"cnpj": cnpj}).fetchall()

        # Skip the first user (keep their CNPJ as is), update the rest
        for user_id, in users[1:]:
            # Append user ID to make CNPJ unique
            new_cnpj = f"{cnpj}-U{user_id}"
            connection.execute(sa.text("""
                UPDATE users SET cnpj = :new_cnpj WHERE id = :user_id
            """), {"new_cnpj": new_cnpj, "user_id": user_id})

    # Now add unique constraint to CNPJ column
    with op.batch_alter_table('users') as batch_op:
        batch_op.create_unique_constraint('uq_users_cnpj', ['cnpj'])


def downgrade() -> None:
    # Remove unique constraint from CNPJ column
    with op.batch_alter_table('users') as batch_op:
        batch_op.drop_constraint('uq_users_cnpj', type_='unique')
