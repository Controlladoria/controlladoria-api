"""add api keys table and migrate roles

Revision ID: manual_api_keys_001
Revises: adb313def57f
Create Date: 2026-01-28

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = 'manual_api_keys_001'
down_revision = 'adb313def57f'
branch_labels = None
depends_on = None


def upgrade():
    # Create user_claims table
    op.create_table(
        'user_claims',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('claim_type', sa.String(length=100), nullable=False, comment='Permission claim (e.g., documents.delete)'),
        sa.Column('claim_value', sa.String(length=255), nullable=False, server_default='true'),
        sa.Column('granted_by_user_id', sa.Integer(), nullable=True),
        sa.Column('granted_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.Column('expires_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_user_claims_user_id', 'user_claims', ['user_id'])
    op.create_index('ix_user_claims_claim_type', 'user_claims', ['claim_type'])
    op.create_index('ix_user_claims_user_claim', 'user_claims', ['user_id', 'claim_type'], unique=True)
    op.create_foreign_key('fk_user_claims_user_id', 'user_claims', 'users', ['user_id'], ['id'], ondelete='CASCADE')
    op.create_foreign_key('fk_user_claims_granted_by', 'user_claims', 'users', ['granted_by_user_id'], ['id'], ondelete='SET NULL')

    # Create api_keys table
    op.create_table(
        'api_keys',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('key_id', sa.String(length=32), nullable=False, comment='First part of API key (visible)'),
        sa.Column('key_hash', sa.String(length=128), nullable=False, comment='Hashed secret part'),
        sa.Column('name', sa.String(length=100), nullable=False, comment='User-friendly name'),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('permissions', postgresql.JSONB(astext_type=sa.Text()), nullable=True, comment='Custom permissions JSON'),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('last_used_at', sa.DateTime(), nullable=True),
        sa.Column('expires_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_api_keys_key_id', 'api_keys', ['key_id'], unique=True)
    op.create_index('ix_api_keys_user_id', 'api_keys', ['user_id'])
    op.create_index('ix_api_keys_user_active', 'api_keys', ['user_id', 'is_active'])
    op.create_foreign_key('fk_api_keys_user_id', 'api_keys', 'users', ['user_id'], ['id'], ondelete='CASCADE')

    # Migrate existing roles from super_admin/member to owner/viewer
    # super_admin -> owner (main account owner)
    # member -> viewer (team member with read-only by default)
    op.execute("""
        UPDATE users
        SET role = 'owner'
        WHERE role = 'super_admin'
    """)

    op.execute("""
        UPDATE users
        SET role = 'viewer'
        WHERE role = 'member'
    """)

    # Add role column to team_invitations
    op.add_column('team_invitations', sa.Column('role', sa.String(length=20), nullable=False, server_default='viewer', comment='Role to assign when invitation is accepted'))

    # Add check constraint for valid roles
    op.create_check_constraint(
        'ck_users_role_valid',
        'users',
        "role IN ('owner', 'admin', 'accountant', 'bookkeeper', 'viewer', 'api_user')"
    )

    # Update default role in database schema (for new registrations)
    op.alter_column('users', 'role', server_default='owner')


def downgrade():
    # Drop api_keys table
    op.drop_constraint('fk_api_keys_user_id', 'api_keys', type_='foreignkey')
    op.drop_index('ix_api_keys_user_active', 'api_keys')
    op.drop_index('ix_api_keys_user_id', 'api_keys')
    op.drop_index('ix_api_keys_key_id', 'api_keys')
    op.drop_table('api_keys')

    # Drop user_claims table
    op.drop_constraint('fk_user_claims_granted_by', 'user_claims', type_='foreignkey')
    op.drop_constraint('fk_user_claims_user_id', 'user_claims', type_='foreignkey')
    op.drop_index('ix_user_claims_user_claim', 'user_claims')
    op.drop_index('ix_user_claims_claim_type', 'user_claims')
    op.drop_index('ix_user_claims_user_id', 'user_claims')
    op.drop_table('user_claims')

    # Remove role column from team_invitations
    op.drop_column('team_invitations', 'role')

    # Drop check constraint
    op.drop_constraint('ck_users_role_valid', 'users', type_='check')

    # Revert role migration
    op.execute("""
        UPDATE users
        SET role = 'super_admin'
        WHERE role = 'owner'
    """)

    op.execute("""
        UPDATE users
        SET role = 'member'
        WHERE role IN ('admin', 'accountant', 'bookkeeper', 'viewer', 'api_user')
    """)
