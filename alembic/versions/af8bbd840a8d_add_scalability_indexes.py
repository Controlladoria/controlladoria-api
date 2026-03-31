"""add_scalability_indexes

Revision ID: af8bbd840a8d
Revises: 71677f4f3cfd
Create Date: 2026-01-28

Critical indexes for 500k+ user scalability
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'af8bbd840a8d'
down_revision: Union[str, None] = 'e61bd5591532'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # NOTE: Removed line_items and transactions - those tables don't exist
    # They are Pydantic models only, not database tables

    # ========== CLIENTS TABLE INDEXES ==========
    # Check if table exists before adding indexes (production may already have them)
    conn = op.get_bind()
    inspector = sa.inspect(conn)

    if 'clients' in inspector.get_table_names():
        existing_indexes = {idx['name'] for idx in inspector.get_indexes('clients')}

        with op.batch_alter_table('clients', schema=None) as batch_op:
            # Composite index for user + type queries
            if 'ix_clients_user_type' not in existing_indexes:
                batch_op.create_index(
                    'ix_clients_user_type',
                    ['user_id', 'client_type'],
                    unique=False
                )

            # Index for name searching
            if 'ix_clients_name' not in existing_indexes:
                batch_op.create_index(
                    'ix_clients_name',
                    ['name'],
                    unique=False
                )

    # ========== AUDIT_LOGS TABLE INDEXES ==========
    # NOTE: audit_logs already has indexes from 9e0505d659e1 migration
    # Skip creating duplicate indexes - they already exist

    # ========== SUBSCRIPTIONS TABLE INDEXES ==========
    # Subscriptions already has indexes from original migration, add composite only
    if 'subscriptions' in inspector.get_table_names():
        existing_indexes = {idx['name'] for idx in inspector.get_indexes('subscriptions')}

        with op.batch_alter_table('subscriptions', schema=None) as batch_op:
            # Composite index for status + period_end (for finding expiring subs)
            if 'ix_subscriptions_status_period_end' not in existing_indexes:
                batch_op.create_index(
                    'ix_subscriptions_status_period_end',
                    ['status', 'current_period_end'],
                    unique=False
                )


def downgrade() -> None:
    # ========== DROP ALL INDEXES IN REVERSE ORDER ==========
    conn = op.get_bind()
    inspector = sa.inspect(conn)

    if 'subscriptions' in inspector.get_table_names():
        existing_indexes = {idx['name'] for idx in inspector.get_indexes('subscriptions')}
        with op.batch_alter_table('subscriptions', schema=None) as batch_op:
            if 'ix_subscriptions_status_period_end' in existing_indexes:
                batch_op.drop_index('ix_subscriptions_status_period_end')

    # audit_logs indexes are managed by the original migration, not here

    if 'clients' in inspector.get_table_names():
        existing_indexes = {idx['name'] for idx in inspector.get_indexes('clients')}
        with op.batch_alter_table('clients', schema=None) as batch_op:
            if 'ix_clients_name' in existing_indexes:
                batch_op.drop_index('ix_clients_name')
            if 'ix_clients_user_type' in existing_indexes:
                batch_op.drop_index('ix_clients_user_type')
