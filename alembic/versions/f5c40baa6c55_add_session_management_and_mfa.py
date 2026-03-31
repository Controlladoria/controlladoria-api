"""add_session_management_and_mfa

Revision ID: f5c40baa6c55
Revises: af8bbd840a8d
Create Date: 2026-01-28

Session tracking to prevent account sharing abuse + MFA foundation
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f5c40baa6c55'
down_revision: Union[str, None] = 'af8bbd840a8d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ========== USER_SESSIONS TABLE ==========
    op.create_table(
        'user_sessions',
        sa.Column('id', sa.String(length=64), primary_key=True),  # Session token (JWT jti or UUID)
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('device_type', sa.String(length=20), nullable=False),  # mobile, desktop, tablet
        sa.Column('device_os', sa.String(length=50), nullable=True),  # Windows, Linux, macOS, iOS, Android
        sa.Column('device_name', sa.String(length=255), nullable=True),  # Browser + OS from user agent
        sa.Column('browser', sa.String(length=50), nullable=True),  # Chrome, Firefox, Safari
        sa.Column('ip_address', sa.String(length=45), nullable=True),  # IPv4 or IPv6
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('last_activity', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('expires_at', sa.DateTime(), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='1'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], name='fk_session_user', ondelete='CASCADE'),
    )

    # Indexes for session queries
    with op.batch_alter_table('user_sessions', schema=None) as batch_op:
        batch_op.create_index('ix_user_sessions_user_id', ['user_id'])
        batch_op.create_index('ix_user_sessions_user_active', ['user_id', 'is_active'])
        batch_op.create_index('ix_user_sessions_expires_at', ['expires_at'])

    # ========== MFA FIELDS ON USERS TABLE ==========
    with op.batch_alter_table('users', schema=None) as batch_op:
        # MFA enabled flag
        batch_op.add_column(sa.Column('mfa_enabled', sa.Boolean(), nullable=False, server_default='0'))

        # TOTP secret (encrypted, for Google Authenticator)
        batch_op.add_column(sa.Column('mfa_secret', sa.String(length=255), nullable=True))

        # Backup codes (JSON array, encrypted)
        batch_op.add_column(sa.Column('mfa_backup_codes', sa.Text(), nullable=True))

        # When MFA was enabled
        batch_op.add_column(sa.Column('mfa_enabled_at', sa.DateTime(), nullable=True))


def downgrade() -> None:
    # Drop MFA fields
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_column('mfa_enabled_at')
        batch_op.drop_column('mfa_backup_codes')
        batch_op.drop_column('mfa_secret')
        batch_op.drop_column('mfa_enabled')

    # Drop sessions table
    with op.batch_alter_table('user_sessions', schema=None) as batch_op:
        batch_op.drop_index('ix_user_sessions_expires_at')
        batch_op.drop_index('ix_user_sessions_user_active')
        batch_op.drop_index('ix_user_sessions_user_id')

    op.drop_table('user_sessions')
