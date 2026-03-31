"""add_email_verification_and_trial_management

Revision ID: c42e9957c528
Revises: 71677f4f3cfd
Create Date: 2026-01-27 17:34:00.036035

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c42e9957c528'
down_revision: Union[str, None] = '71677f4f3cfd'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add email verification token
    with op.batch_alter_table('users') as batch_op:
        batch_op.add_column(sa.Column('email_verification_token', sa.String(255), nullable=True))
        batch_op.create_index('ix_users_email_verification_token', ['email_verification_token'])

    # Add trial end date
    with op.batch_alter_table('users') as batch_op:
        batch_op.add_column(sa.Column('trial_end_date', sa.DateTime(), nullable=True))

    # Set trial_end_date for existing users (15 days from their created_at)
    # Different syntax for PostgreSQL vs SQLite
    connection = op.get_bind()
    if connection.dialect.name == 'postgresql':
        # PostgreSQL syntax
        op.execute("""
            UPDATE users
            SET trial_end_date = created_at + INTERVAL '15 days'
            WHERE trial_end_date IS NULL
        """)
    else:
        # SQLite syntax
        op.execute("""
            UPDATE users
            SET trial_end_date = datetime(created_at, '+15 days')
            WHERE trial_end_date IS NULL
        """)


def downgrade() -> None:
    # Remove trial end date
    with op.batch_alter_table('users') as batch_op:
        batch_op.drop_column('trial_end_date')

    # Remove email verification token
    with op.batch_alter_table('users') as batch_op:
        batch_op.drop_index('ix_users_email_verification_token')
        batch_op.drop_column('email_verification_token')
