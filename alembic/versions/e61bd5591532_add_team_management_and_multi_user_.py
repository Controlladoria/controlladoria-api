"""add_team_management_and_multi_user_support

Revision ID: e61bd5591532
Revises: d6af064b42ed
Create Date: 2026-01-28 16:39:35.377406

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e61bd5591532'
down_revision: Union[str, None] = 'd6af064b42ed'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ========== 1. EXTEND USERS TABLE FOR TEAM MANAGEMENT ==========

    with op.batch_alter_table('users', schema=None) as batch_op:
        # Role: 'super_admin' (default) or 'member'
        batch_op.add_column(sa.Column('role', sa.String(length=20), nullable=False, server_default='super_admin'))

        # Parent user (super admin) - NULL for super admins, points to admin for members
        batch_op.add_column(sa.Column('parent_user_id', sa.Integer(), nullable=True))

        # Who invited this user
        batch_op.add_column(sa.Column('invited_by_user_id', sa.Integer(), nullable=True))

        # When invitation was sent
        batch_op.add_column(sa.Column('invited_at', sa.DateTime(), nullable=True))

        # Add foreign keys
        batch_op.create_foreign_key('fk_parent_user', 'users', ['parent_user_id'], ['id'])
        batch_op.create_foreign_key('fk_invited_by', 'users', ['invited_by_user_id'], ['id'])

        # Add indexes
        batch_op.create_index('ix_users_role', ['role'])
        batch_op.create_index('ix_users_parent_user_id', ['parent_user_id'])

    # ========== 2. CREATE TEAM_INVITATIONS TABLE ==========

    op.create_table(
        'team_invitations',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('inviter_user_id', sa.Integer(), nullable=False),
        sa.Column('email', sa.String(length=255), nullable=False),
        sa.Column('token', sa.String(length=255), nullable=False),
        sa.Column('expires_at', sa.DateTime(), nullable=False),
        sa.Column('accepted_at', sa.DateTime(), nullable=True),
        sa.Column('is_cancelled', sa.Boolean(), nullable=False, server_default='0'),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.ForeignKeyConstraint(['inviter_user_id'], ['users.id'], name='fk_inviter'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('token', name='uq_invitation_token')
    )

    with op.batch_alter_table('team_invitations', schema=None) as batch_op:
        batch_op.create_index('ix_team_invitations_email', ['email'])
        batch_op.create_index('ix_team_invitations_token', ['token'])
        batch_op.create_index('ix_team_invitations_inviter_user_id', ['inviter_user_id'])

    # ========== 3. EXTEND SUBSCRIPTIONS TABLE ==========

    with op.batch_alter_table('subscriptions', schema=None) as batch_op:
        # Maximum users allowed on this subscription plan
        batch_op.add_column(sa.Column('max_users', sa.Integer(), nullable=False, server_default='1'))


def downgrade() -> None:
    # ========== 3. REMOVE SUBSCRIPTIONS EXTENSION ==========

    with op.batch_alter_table('subscriptions', schema=None) as batch_op:
        batch_op.drop_column('max_users')

    # ========== 2. DROP TEAM_INVITATIONS TABLE ==========

    with op.batch_alter_table('team_invitations', schema=None) as batch_op:
        batch_op.drop_index('ix_team_invitations_inviter_user_id')
        batch_op.drop_index('ix_team_invitations_token')
        batch_op.drop_index('ix_team_invitations_email')

    op.drop_table('team_invitations')

    # ========== 1. REMOVE USERS TABLE EXTENSIONS ==========

    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_index('ix_users_parent_user_id')
        batch_op.drop_index('ix_users_role')
        batch_op.drop_constraint('fk_invited_by', type_='foreignkey')
        batch_op.drop_constraint('fk_parent_user', type_='foreignkey')
        batch_op.drop_column('invited_at')
        batch_op.drop_column('invited_by_user_id')
        batch_op.drop_column('parent_user_id')
        batch_op.drop_column('role')
