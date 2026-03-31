"""add_mfa_method_and_trusted_devices

Revision ID: a55ee899db08
Revises: 95b88f3264bc
Create Date: 2026-02-02 21:23:20.829446

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a55ee899db08'
down_revision: Union[str, None] = '95b88f3264bc'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add MFA method selection to users table
    # Values: 'totp' (Google Authenticator), 'email', or NULL (MFA disabled)
    op.add_column('users', sa.Column('mfa_method', sa.String(length=20), nullable=True))

    # Add trusted device tracking to user_sessions table
    # device_fingerprint: hash of user agent + IP for device identification
    # trusted_until: when trust expires (30 days from trust date)
    op.add_column('user_sessions', sa.Column('is_trusted_device', sa.Boolean(), nullable=False, server_default='false'))
    op.add_column('user_sessions', sa.Column('device_fingerprint', sa.String(length=255), nullable=True))
    op.add_column('user_sessions', sa.Column('trusted_until', sa.DateTime(), nullable=True))


def downgrade() -> None:
    # Remove trusted device fields from user_sessions
    op.drop_column('user_sessions', 'trusted_until')
    op.drop_column('user_sessions', 'device_fingerprint')
    op.drop_column('user_sessions', 'is_trusted_device')

    # Remove MFA method from users
    op.drop_column('users', 'mfa_method')
